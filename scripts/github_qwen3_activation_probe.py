from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import urllib.request

from scripts.benchmark_reasoning_provider import CASES, evaluate
from scripts.local_reasoning_provider import LocalReasoningModel

MODEL = "Qwen/Qwen3-4B-Instruct-2507"


def validate_code_response(text: str) -> None:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object")
    payload, _ = json.JSONDecoder().raw_decode(text, start)
    if set(payload) != {"files"} or set(payload["files"]) != {"genesis/probe.py"}:
        raise ValueError("Unexpected proposal scope")
    source = payload["files"]["genesis/probe.py"]
    if not isinstance(source, str) or len(source) > 2000:
        raise ValueError("Invalid source")
    tree = ast.parse(source)
    permitted = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return,
                 ast.BinOp, ast.Add, ast.Name, ast.Load, ast.Constant)
    if any(not isinstance(node, permitted) for node in ast.walk(tree)):
        raise ValueError("Unsafe/nonminimal probe syntax")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Expected one function")
    fn = tree.body[0]
    if (fn.name != "add" or [arg.arg for arg in fn.args.args] != ["a", "b"]
        or fn.decorator_list or fn.args.defaults or fn.args.vararg or fn.args.kwarg
        or fn.args.kwonlyargs or fn.args.posonlyargs):
        raise ValueError("Unexpected function signature")
    if any(node.id not in {"a", "b"} for node in ast.walk(tree) if isinstance(node, ast.Name)):
        raise ValueError("Unexpected identifier")
    namespace = {"__builtins__": {}}
    exec(compile(tree, "<isolated-model-probe>", "exec"), namespace)
    for a, b, expected in [(2, 3, 5), (-2, 3, 1), (0, 0, 0), (1000000, -1, 999999)]:
        if namespace["add"](a, b) != expected:
            raise ValueError("Functional probe failed")


def timed_reason(model, prompt, budget):
    def timeout(_signum, _frame):
        raise TimeoutError("Inference exceeded 180 seconds")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    try:
        return model.reason(prompt, max_new_tokens=budget)
    finally:
        signal.alarm(0)


def main():
    import torch
    import resource
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(2)
    request = urllib.request.Request("https://huggingface.co/api/models/" + MODEL,
                                     headers={"User-Agent": "Genesis-Qwen3-Activation"})
    with urllib.request.urlopen(request, timeout=30) as response:
        metadata = json.load(response)
    if metadata.get("cardData", {}).get("license") != "apache-2.0":
        raise RuntimeError("Model license mismatch")
    registry_path = Path(__file__).resolve().parents[1] / "config/provider_candidates.json"
    registered = next(p for p in json.loads(registry_path.read_text(encoding="utf-8"))["providers"]
                      if p["provider_id"] == "qwen3-4b-instruct-2507-optional")
    revision = (registered["metadata"]["model_revision"] if registered["state"] == "ACTIVE"
                else metadata["sha"])
    if len(revision) != 40:
        raise RuntimeError("Model revision not pinned")
    begin = time.monotonic()
    model = LocalReasoningModel.__new__(LocalReasoningModel)
    from transformers import StoppingCriteria, StoppingCriteriaList
    model.torch = torch
    model.StoppingCriteria = StoppingCriteria
    model.StoppingCriteriaList = StoppingCriteriaList
    model.model_id = MODEL
    model.max_new_tokens = 512
    model.tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=revision, trust_remote_code=False)
    model.model = AutoModelForCausalLM.from_pretrained(
        MODEL, revision=revision, trust_remote_code=False,
        torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    model.model.eval()
    results = []
    for case in CASES:
        response = timed_reason(model, case["prompt"], 96)
        passed, evidence = evaluate(response, case)
        results.append({"id": case["id"], "passed": passed, **evidence})
    prompt = ('Write a minimal Python addition function as a JSON proposal. '
              'Required exact JSON schema: {"files":{"genesis/probe.py":"PYTHON_SOURCE_STRING"}}. '
              'The files value is an object, not a list. The only key is genesis/probe.py. '
              'Replace PYTHON_SOURCE_STRING with a SINGLE LINE defining def add(a, b): and returning a + b. '
              'No imports, annotations, defaults, decorators, helper functions or calls. '
              'Return the JSON object only. Keep Python source on one line; no newline characters or escape sequences.')
    response = timed_reason(model, prompt, 256)
    print("structured_coding_response=" + repr(response), flush=True)
    try:
        validate_code_response(response)
        coding_passed, coding_error = True, None
    except (ValueError, SyntaxError, TypeError, KeyError) as error:
        coding_passed, coding_error = False, str(error)
    results.append({"id": "structured_coding_and_functional_checks", "passed": coding_passed,
                    "response": response[:2000], "error": coding_error})
    report = {"model_id": MODEL, "model_revision": revision, "license": "apache-2.0",
              "runner": os.environ["BENCHMARK_RUNNER"], "workflow_run": int(os.environ["GITHUB_RUN_ID"]),
              "source_sha": os.environ["GITHUB_SHA"], "trust_remote_code": False,
              "passed": all(case["passed"] for case in results), "cases": results,
              "elapsed_seconds": round(time.monotonic() - begin, 2),
              "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "scope": "Basic inference, identity/safety and bounded coding smoke qualification; not a full repair benchmark"}
    if report["max_rss_kib"] > 14 * 1024 * 1024 or report["elapsed_seconds"] > 1200:
        report["passed"] = False
    task = os.environ.get("GENESIS_TASK", "").strip()
    if task and report["passed"] and report["runner"] == "benchmark_a":
        if len(task) > 8000:
            raise ValueError("Manual task exceeds 8000 characters")
        report["manual_task"] = {"prompt": task, "response": timed_reason(model, task, 512),
                                 "mode": "advisory_only_no_repository_or_issue_mutation"}
    path = Path("qwen3-benchmark-" + os.environ["BENCHMARK_RUNNER"] + ".json")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("artifact_sha256=" + hashlib.sha256(path.read_bytes()).hexdigest())
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

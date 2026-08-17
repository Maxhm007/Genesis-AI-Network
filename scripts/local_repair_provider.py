from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MAX_ATTEMPTS = 4
PROTECTED = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


def _payload(prompt_text: str) -> dict:
    try:
        value = json.loads(prompt_text)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def context_files(prompt_text: str) -> dict[str, str]:
    payload = _payload(prompt_text)
    failure = str(payload.get("failure_text", prompt_text))
    provided = payload.get("relevant_files") if isinstance(payload.get("relevant_files"), dict) else {}
    candidates: list[str] = []
    for relative in provided:
        normalized = str(relative).replace("\\", "/")
        if normalized not in candidates:
            candidates.append(normalized)
    for match in re.findall(r"(?:genesis|tests)/[A-Za-z0-9_./-]+\.py", failure):
        normalized = match.replace("\\", "/")
        if normalized not in candidates:
            candidates.append(normalized)

    result: dict[str, str] = {}
    for relative in candidates[:6]:
        path = ROOT / relative
        if path.exists() and path.is_file():
            result[relative] = path.read_text(encoding="utf-8", errors="replace")[:9000]
    return result


def numbered_context(files: dict[str, str]) -> str:
    chunks: list[str] = []
    for relative, text in files.items():
        numbered = "\n".join(f"{i}|{line}" for i, line in enumerate(text.splitlines(), start=1))
        chunks.append(f"\n--- FILE {relative} ---\n{numbered}")
    return "".join(chunks)


def _normalize_model_json(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*```\s*$", "", normalized)

    def replace_triple_quoted_new(match: re.Match[str]) -> str:
        code = textwrap.dedent(match.group(1)).strip("\n")
        return '"new": ' + json.dumps(code)

    normalized = re.sub(
        r'"new"\s*:\s*"""(.*?)"""',
        replace_triple_quoted_new,
        normalized,
        flags=re.DOTALL,
    )
    return normalized


def _balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _load_model_proposal(raw: str) -> dict:
    normalized = _normalize_model_json(raw)
    block = _balanced_json(normalized)
    if not block:
        raise ValueError("response did not contain a complete JSON object")
    proposal = json.loads(block)
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be a JSON object")
    return proposal


def _apply_line_edit(current: str, start: int, end: int, new: str) -> str:
    lines = current.splitlines(keepends=True)
    if start < 1 or end < start or end > len(lines):
        raise ValueError("line edit range is invalid")
    removed = "".join(lines[start - 1 : end])
    replacement = new
    if removed.endswith(("\n", "\r")) and replacement and not replacement.endswith(("\n", "\r")):
        replacement += "\n"
    return "".join(lines[: start - 1]) + replacement + "".join(lines[end:])


def infer_function_target(prompt_text: str, target_path: str | None, source: str) -> tuple[str, int, int] | None:
    if not target_path:
        return None
    payload = _payload(prompt_text)
    failure = str(payload.get("failure_text", ""))
    try:
        tree = ast.parse(source, filename=target_path)
    except Exception:
        return None
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(node, "end_lineno", None)
    }
    call_names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", failure)
    matches: list[str] = []
    for name in call_names:
        if name in functions and name not in matches:
            matches.append(name)
    if len(matches) != 1:
        return None
    node = functions[matches[0]]
    return matches[0], int(node.lineno), int(node.end_lineno)


def validate_function_contract(replacement: str, source: str, target_span: tuple[str, int, int]) -> str:
    function_name, start, end = target_span
    try:
        original_tree = ast.parse(source)
        original = next(
            node for node in ast.walk(original_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
            and int(node.lineno) == start
            and int(getattr(node, "end_lineno", -1)) == end
        )
        replacement_tree = ast.parse(replacement)
    except Exception as exc:
        return f"function-contract parse failed: {exc}"

    if len(replacement_tree.body) != 1 or not isinstance(replacement_tree.body[0], type(original)):
        return "replacement must contain exactly the target function and no module imports or extra top-level code"
    candidate = replacement_tree.body[0]
    if candidate.name != original.name:
        return f"replacement must keep function name {original.name}"
    if ast.dump(candidate.args, include_attributes=False) != ast.dump(original.args, include_attributes=False):
        return (
            "replacement must preserve the exact existing function signature and parameter contract; "
            "change only the function body. If a new top-level behavior is supplied through an existing **kwargs mapping, "
            "extract only that controlling key and preserve all unrelated kwargs in the mapping"
        )
    if ast.dump(candidate.returns, include_attributes=False) != ast.dump(original.returns, include_attributes=False):
        return "replacement must preserve the existing return annotation"
    return ""


def _pin_target(raw: str, target_path: str | None, target_span: tuple[str, int, int] | None) -> str:
    if not target_path:
        return _normalize_model_json(raw)
    try:
        proposal = _load_model_proposal(raw)
    except Exception:
        return _normalize_model_json(raw)
    edit = proposal.get("edit")
    if edit is None and isinstance(proposal.get("edits"), list) and len(proposal["edits"]) == 1:
        edit = proposal["edits"][0]
    if isinstance(edit, dict):
        edit["path"] = target_path
        if target_span:
            _, start, end = target_span
            edit["start_line"] = start
            edit["end_line"] = end
        proposal["edit"] = edit
        proposal.pop("edits", None)
    return json.dumps(proposal)


def validate_compact_proposal(raw: str, files: dict[str, str]) -> tuple[dict | None, str, dict | None]:
    try:
        proposal = _load_model_proposal(raw)
    except Exception as exc:
        return None, f"response JSON could not be parsed: {exc}", None

    edit = proposal.get("edit")
    if edit is None and isinstance(proposal.get("edits"), list) and len(proposal["edits"]) == 1:
        edit = proposal["edits"][0]
    if not isinstance(edit, dict):
        return None, "proposal must contain exactly one edit", None

    path = str(edit.get("path", "")).replace("\\", "/").lstrip("./")
    start = edit.get("start_line")
    end = edit.get("end_line")
    new = edit.get("new")
    debug_edit = {"path": path, "start_line": start, "end_line": end, "new": new}
    if path in PROTECTED or not path.startswith("genesis/"):
        return None, "repair edit must target production code under genesis/", debug_edit
    if path not in files:
        return None, "repair edit path must be one of the supplied production context files", debug_edit
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
        return None, "start_line and end_line must be integers", debug_edit
    if not isinstance(new, str) or not new.strip():
        return None, "replacement text must be non-empty", debug_edit
    try:
        rendered = _apply_line_edit(files[path], start, end, new)
        ast.parse(rendered, filename=path)
    except SyntaxError as exc:
        return None, f"edited Python is invalid: {exc.msg} at line {exc.lineno}", debug_edit
    except Exception as exc:
        return None, str(exc), debug_edit

    return {
        "title": str(proposal.get("title") or proposal.get("repair_title") or "Genesis compact autonomous repair"),
        "rationale": str(proposal.get("rationale", "Smallest bounded production-code repair")),
        "files": {path: rendered},
    }, "", debug_edit


def validate_candidate_tests(proposal: dict) -> tuple[bool, str]:
    files = proposal.get("files") if isinstance(proposal, dict) else None
    if not isinstance(files, dict) or not files:
        return False, "candidate contains no rendered production files"
    originals: dict[str, str] = {}
    try:
        for relative, rendered in files.items():
            path = ROOT / relative
            originals[relative] = path.read_text(encoding="utf-8")
            path.write_text(str(rendered), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        proc = subprocess.run(
            [os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
            timeout=90,
        )
        output = (proc.stdout + "\n" + proc.stderr)[-6000:]
        return proc.returncode == 0, output
    except Exception as exc:
        return False, f"candidate validation error: {exc}"
    finally:
        for relative, original in originals.items():
            (ROOT / relative).write_text(original, encoding="utf-8")


def compact_problem(prompt_text: str) -> str:
    payload = _payload(prompt_text)
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    failure = str(payload.get("failure_text", ""))[-5000:]
    return (
        f"DIAGNOSIS_CATEGORY: {diagnosis.get('category', 'unknown')}\n"
        f"DIAGNOSIS_SUMMARY: {diagnosis.get('summary', '')}\n"
        "FAILING_TEST_OUTPUT:\n"
        f"{failure}\n"
    )


class LocalRepairModel:
    def __init__(self, model_id: str) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=False,
            torch_dtype="auto",
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    def _generate(self, messages: list[dict]) -> str:
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=8000)
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=320,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()

    def reason(self, prompt: str) -> str:
        files = context_files(prompt)
        production_files = {path: text for path, text in files.items() if path.startswith("genesis/")}
        if not production_files:
            raise RuntimeError("no production source context available for autonomous repair")
        context = numbered_context(production_files)
        problem = compact_problem(prompt)
        allowed_paths = list(production_files)
        pinned_target = allowed_paths[0] if len(allowed_paths) == 1 else None
        target_span = infer_function_target(prompt, pinned_target, production_files[pinned_target]) if pinned_target else None
        target_instruction = (
            f"TARGET_FILE is fixed by the repair controller to {pinned_target}. Do not choose a path. "
            if pinned_target
            else "Choose path only from ALLOWED_PRODUCTION_FILES. "
        )
        if target_span:
            function_name, start, end = target_span
            target_instruction += (
                f"TARGET_FUNCTION is {function_name}, lines {start}-{end}. Rewrite the COMPLETE function only. "
                "You MUST keep the exact original function signature and parameters; change only its body. "
                "The controller fixes the file and line range automatically. "
            )
        system = (
            "You are the bounded software-debugging specialist for Genesis AI. Return JSON only. "
            "Fix the production root cause while preserving all existing passing behavior and public function contracts. "
            "Never edit tests. Never change protected identity, workflows, permissions, validation/quorum, signing, secrets, "
            "or self-development protections. "
            + target_instruction
        )
        feedback = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if target_span:
                schema = '{"title":"repair title","rationale":"root-cause explanation","edit":{"new":"COMPLETE corrected function definition with newline escapes"}}'
            elif pinned_target:
                schema = '{"title":"repair title","rationale":"root-cause explanation","edit":{"start_line":INTEGER,"end_line":INTEGER,"new":"actual replacement Python code"}}'
            else:
                schema = '{"title":"repair title","rationale":"root-cause explanation","edit":{"path":"ONE OF ALLOWED_PRODUCTION_FILES","start_line":INTEGER,"end_line":INTEGER,"new":"actual replacement Python code"}}'
            user = (
                problem
                + f"\nALLOWED_PRODUCTION_FILES: {json.dumps(allowed_paths)}"
                + (f"\nTARGET_FILE: {pinned_target}" if pinned_target else "")
                + (f"\nTARGET_FUNCTION: {target_span[0]} lines {target_span[1]}-{target_span[2]}" if target_span else "")
                + "\nNUMBERED_CONTEXT:"
                + context
                + "\nReturn a real repair, not placeholders, TODO, or pass."
                + "\nDo not hard-code values from the failing test. Preserve the function's old default behavior while supporting the failing call generically."
                + "\nIf the existing function accepts **kwargs/details, preserve unrelated keys there; extract only a key that must control a top-level field."
                + "\nOUTPUT_SCHEMA: "
                + schema
            )
            if feedback:
                user += "\nPREVIOUS_CANDIDATE_FAILED_VALIDATION:\n" + feedback + "\nUse the validation failure to produce a different corrected implementation. JSON only."
            raw = self._generate([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            raw = _pin_target(raw, pinned_target, target_span)
            proposal, error, edit = validate_compact_proposal(raw, production_files)
            if proposal is not None:
                if target_span and edit is not None:
                    contract_error = validate_function_contract(str(edit.get("new", "")), production_files[pinned_target], target_span)
                    if contract_error:
                        feedback = contract_error
                        print(json.dumps({"repair_attempt": attempt, "status": "function_contract_rejected", "reason": contract_error, "edit": edit}), flush=True)
                        continue
                passed, validation_output = validate_candidate_tests(proposal)
                if passed:
                    print(json.dumps({"repair_attempt": attempt, "status": "proposal_validated", "proposal": proposal.get("title"), "edit": edit}), flush=True)
                    return json.dumps(proposal, sort_keys=True)
                feedback = "candidate failed full test validation\n" + validation_output
                print(json.dumps({"repair_attempt": attempt, "status": "candidate_tests_failed", "reason": "candidate failed full test validation", "edit": edit, "test_output": validation_output[-1800:]}), flush=True)
                continue
            print(json.dumps({"repair_attempt": attempt, "status": "proposal_rejected", "reason": error, "edit": edit, "output": raw[:600]}), flush=True)
            feedback = f"{error}. Previous edit: {json.dumps(edit)}. Previous output: {raw[:500]}"
        raise RuntimeError(f"repair proposal invalid after {MAX_ATTEMPTS} attempts: {feedback[:1200]}")


class Handler(BaseHTTPRequestHandler):
    model: LocalRepairModel | None = None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ready", "provider": "genesis-local-repair", "model": self.model.model_id if self.model else None})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/reason":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = str(payload.get("prompt", ""))
        if not prompt:
            self._json(400, {"error": "prompt required"})
            return
        try:
            response = self.model.reason(prompt) if self.model else ""
            self._json(200, {"response": response})
        except Exception as exc:
            print(json.dumps({"status": "repair_error", "error": str(exc)[:1200]}), flush=True)
            self._json(500, {"error": str(exc)})

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    Handler.model = LocalRepairModel(args.model)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"status": "ready", "provider": "genesis-local-repair", "model": args.model}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
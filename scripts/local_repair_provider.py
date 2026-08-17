from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MAX_ATTEMPTS = 3


def _prompt_payload(prompt_text: str) -> dict:
    try:
        value = json.loads(prompt_text)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def relevant_context(prompt_text: str) -> str:
    payload = _prompt_payload(prompt_text)
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

    chunks: list[str] = []
    for relative in candidates[:6]:
        path = ROOT / relative
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"\n--- FILE {relative} ---\n{text[:9000]}")
    return "".join(chunks)


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


def validate_generated_proposal(raw: str, prompt_text: str) -> tuple[dict | None, str]:
    block = _balanced_json(raw.strip())
    if not block:
        return None, "response did not contain a complete JSON object"
    try:
        proposal = json.loads(block)
    except Exception as exc:
        return None, f"response JSON could not be parsed: {exc}"
    if not isinstance(proposal, dict):
        return None, "proposal must be a JSON object"
    files = proposal.get("files")
    if not isinstance(files, dict) or not files:
        return None, "proposal must contain a non-empty files mapping"
    if not all(isinstance(path, str) and isinstance(content, str) for path, content in files.items()):
        return None, "all proposal files must map paths to complete text contents"

    payload = _prompt_payload(prompt_text)
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    category = str(diagnosis.get("category", ""))
    stale_test_categories = {"provider_mode_expectation", "selfdev_catalog_marker_mismatch"}
    if category not in stale_test_categories and all(path.startswith("tests/") for path in files):
        return None, "test-only repairs are forbidden for this failure; fix the production root cause"
    return proposal, ""


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
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=12000)
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=1800,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()

    def reason(self, prompt: str) -> str:
        context = relevant_context(prompt)
        system = (
            "You are the bounded software-debugging specialist for Genesis AI. "
            "Return JSON only with exactly these top-level keys: title, rationale, files. "
            "files maps repository-relative paths to COMPLETE replacement file contents. "
            "Never modify GENESIS_CONSTITUTION.md, GENESIS_BLOCK.json, workflow permissions, "
            "validator quorum/signing rules, or self-development protections. Never skip, xfail, "
            "delete, or weaken tests merely to make them pass. For ordinary failures, repair production code, "
            "not the test that exposed the defect. Prefer the smallest root-cause fix."
        )
        feedback = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            user = prompt + context
            if feedback:
                user += (
                    "\n\nPREVIOUS PROPOSAL REJECTED: "
                    + feedback
                    + "\nReturn a corrected complete JSON proposal only."
                )
            raw = self._generate([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            proposal, error = validate_generated_proposal(raw, prompt)
            if proposal is not None:
                return json.dumps(proposal, sort_keys=True)
            feedback = f"attempt {attempt}: {error}; previous output: {raw[:1200]}"
        raise RuntimeError(f"repair proposal invalid after {MAX_ATTEMPTS} attempts: {feedback[:1800]}")


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

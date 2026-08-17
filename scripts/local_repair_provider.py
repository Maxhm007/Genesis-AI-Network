from __future__ import annotations

import argparse
import ast
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MAX_ATTEMPTS = 3
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


def _apply_line_edit(current: str, start: int, end: int, new: str) -> str:
    lines = current.splitlines(keepends=True)
    if start < 1 or end < start or end > len(lines):
        raise ValueError("line edit range is invalid")
    removed = "".join(lines[start - 1 : end])
    replacement = new
    if removed.endswith(("\n", "\r")) and replacement and not replacement.endswith(("\n", "\r")):
        replacement += "\n"
    return "".join(lines[: start - 1]) + replacement + "".join(lines[end:])


def validate_compact_proposal(raw: str, files: dict[str, str]) -> tuple[dict | None, str, dict | None]:
    block = _balanced_json(raw.strip())
    if not block:
        return None, "response did not contain a complete JSON object", None
    try:
        proposal = json.loads(block)
    except Exception as exc:
        return None, f"response JSON could not be parsed: {exc}", None
    if not isinstance(proposal, dict):
        return None, "proposal must be a JSON object", None

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
        "title": str(proposal.get("title", "Genesis compact autonomous repair")),
        "rationale": str(proposal.get("rationale", "Smallest bounded production-code repair")),
        "files": {path: rendered},
    }, "", debug_edit


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
                max_new_tokens=700,
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
        system = (
            "You are the bounded software-debugging specialist for Genesis AI. Return JSON only. "
            "Fix the production root cause of the failing test with exactly ONE smallest line-range edit. "
            "Never edit tests. Never change protected identity, workflows, permissions, validation/quorum, signing, secrets, "
            "or self-development protections. Use 1-based inclusive line numbers exactly from NUMBERED_CONTEXT."
        )
        feedback = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            user = (
                problem
                + "\nNUMBERED_CONTEXT:"
                + context
                + '\nOUTPUT_JSON: {"title":"short repair title","rationale":"why this fixes the root cause","edit":{"path":"genesis/file.py","start_line":1,"end_line":1,"new":"replacement text"}}'
            )
            if feedback:
                user += "\nREJECTION_FEEDBACK: " + feedback + "\nReturn corrected JSON only."
            raw = self._generate([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            proposal, error, edit = validate_compact_proposal(raw, production_files)
            if proposal is not None:
                print(json.dumps({"repair_attempt": attempt, "status": "proposal_valid", "proposal": proposal.get("title"), "edit": edit}), flush=True)
                return json.dumps(proposal, sort_keys=True)
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

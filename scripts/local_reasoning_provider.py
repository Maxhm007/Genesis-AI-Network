from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODEL = "Qwen/Qwen3-0.6B"
DEFAULT_MAX_NEW_TOKENS = 512
MAX_ALLOWED_NEW_TOKENS = 768
MAX_PROVIDER_PROMPT_CHARS = 14_000
ROLE_MAX_NEW_TOKENS = {
    "genesis_internal_code_reviewer": 128,
    "bounded_coding_engineer": 128,
}
ROLE_MAX_COMPLETION_TOKENS = {
    "bounded_coding_engineer": 160,
}
COMPACT_EDIT_END_MARKER = "END_NEW"


def _prompt_role(prompt: str) -> str | None:
    for line in prompt.splitlines()[:8]:
        if line.startswith("ROLE:"):
            return line.split(":", 1)[1].strip()
    return None


def _single_edit_from_example(text: str) -> tuple[dict, int, int] | None:
    """Extract one complete edit already present in a prompt schema example."""
    start = text.find("{")
    while start >= 0:
        try:
            value, end = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            edits = value.get("edits")
            if isinstance(edits, list) and len(edits) == 1 and isinstance(edits[0], dict):
                return edits[0], start, end
            if isinstance(value.get("path"), str) and isinstance(value.get("new"), str):
                return value, start, end
        start = text.find("{", start + 1)
    return None


def _compact_single_edit_example(text: str) -> str:
    """Replace one JSON edit example with a quote-free bounded line protocol."""
    found = _single_edit_from_example(text)
    if found is None:
        return text
    edit, start, end = found
    path = edit.get("path")
    start_line = edit.get("start_line")
    end_line = edit.get("end_line")
    new = edit.get("new")
    if (
        not isinstance(path, str)
        or not isinstance(start_line, int)
        or isinstance(start_line, bool)
        or not isinstance(end_line, int)
        or isinstance(end_line, bool)
        or not isinstance(new, str)
    ):
        return text
    block = (
        f"PATH: {path}\n"
        f"START: {start_line}\n"
        f"END: {end_line}\n"
        "NEW:\n"
        f"{new}\n"
        f"{COMPACT_EDIT_END_MARKER}"
    )
    tail = text[end:]
    if tail and not tail.startswith("\n"):
        tail = "\n" + tail.lstrip()
    prefix = text[:start].rstrip()
    return prefix + "\n" + block + tail


def simplify_bounded_coding_prompt(prompt: str) -> str:
    """Use a strict line protocol so the small coding model need not escape code as JSON.

    CodingModule still receives JSON after this provider strictly translates a complete
    line-protocol edit. The downstream path/range/AST/security checks are unchanged, and
    legacy JSON output remains accepted unchanged.
    """
    if _prompt_role(prompt) != "bounded_coding_engineer":
        return prompt
    rows: list[str] = []
    for line in prompt.splitlines():
        if line.startswith("OUTPUT: JSON only in this shape:"):
            line = _compact_single_edit_example(line).replace(
                "OUTPUT: JSON only in this shape:",
                "OUTPUT: Return ONLY this exact one-edit block; do not use JSON:",
                1,
            )
        elif "Return ONLY the same JSON shape as:" in line:
            line = _compact_single_edit_example(line).replace(
                "Return ONLY the same JSON shape as:",
                "Return ONLY this exact one-edit block; do not use JSON:",
                1,
            )
        rows.append(line)
    return "\n".join(rows)


def compact_prompt(prompt: str) -> str:
    """Keep bounded instructions/objective and recent repository context."""
    if len(prompt) <= MAX_PROVIDER_PROMPT_CHARS:
        return prompt
    head = MAX_PROVIDER_PROMPT_CHARS // 2
    tail = MAX_PROVIDER_PROMPT_CHARS - head
    return prompt[:head] + "\n[...bounded context elided...]\n" + prompt[-tail:]


def role_token_budget(prompt: str) -> int | None:
    """Return a narrow initial output cap for roles that only need compact decisions."""
    role = _prompt_role(prompt)
    return ROLE_MAX_NEW_TOKENS.get(role) if role else None


def role_completion_budget(prompt: str) -> int | None:
    """Return the maximum total generation budget for latency-sensitive roles."""
    role = _prompt_role(prompt)
    return ROLE_MAX_COMPLETION_TOKENS.get(role) if role else None


def balanced_json_object_complete(text: str) -> bool:
    """Return True once text contains one complete top-level JSON object.

    Text before the first opening brace is tolerated because small local models
    sometimes emit a short preamble. Braces inside quoted strings are ignored.
    """
    start = text.find("{")
    if start < 0:
        return False
    depth = 0
    in_string = False
    escaped = False
    for char in text[start:]:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
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
                return True
            if depth < 0:
                return False
    return False


def parse_compact_edit(text: str) -> dict:
    """Parse one exact line-protocol edit without guessing or repairing missing fields."""
    rows = text.strip().splitlines()
    if len(rows) < 5:
        raise ValueError("compact edit is incomplete")
    if not rows[0].startswith("PATH: "):
        raise ValueError("compact edit must start with PATH")
    if not rows[1].startswith("START: "):
        raise ValueError("compact edit must contain START")
    if not rows[2].startswith("END: "):
        raise ValueError("compact edit must contain END")
    if rows[3] != "NEW:" or rows[-1] != COMPACT_EDIT_END_MARKER:
        raise ValueError("compact edit delimiters are invalid")

    path = rows[0].removeprefix("PATH: ").strip()
    start_text = rows[1].removeprefix("START: ").strip()
    end_text = rows[2].removeprefix("END: ").strip()
    if not path or not start_text.isdecimal() or not end_text.isdecimal():
        raise ValueError("compact edit path/range is invalid")
    start_line = int(start_text)
    end_line = int(end_text)
    if start_line < 1 or end_line < start_line:
        raise ValueError("compact edit range is invalid")
    new = "\n".join(rows[4:-1])
    return {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "new": new,
    }


def compact_edit_block_complete(text: str) -> bool:
    """Return True only when one strict compact edit block is complete."""
    try:
        parse_compact_edit(text)
    except ValueError:
        return False
    return True


def bounded_coding_output_complete(text: str) -> bool:
    """Recognize either legacy JSON or the compact edit protocol."""
    return balanced_json_object_complete(text) or compact_edit_block_complete(text)


def normalize_bounded_coding_output(text: str) -> str:
    """Translate a complete compact edit to JSON; leave malformed output untouched.

    Leaving malformed output untouched is intentional: CodingModule will reject it.
    No path, range, replacement text, or missing delimiter is invented here.
    """
    if balanced_json_object_complete(text):
        return text
    try:
        edit = parse_compact_edit(text)
    except ValueError:
        return text
    return json.dumps(edit, separators=(",", ":"))


def json_completion_reserve_tokens(
    text: str,
    *,
    generated_tokens: int,
    requested_budget: int,
    configured_budget: int,
) -> int:
    """Return a bounded reserve when a recognized coding output was cut off.

    The legacy function name is retained for compatibility. The reserve now also
    understands the compact edit protocol used by bounded coding roles.
    """
    requested = max(0, int(requested_budget))
    configured = max(0, int(configured_budget))
    if configured <= requested or generated_tokens < requested:
        return 0
    if bounded_coding_output_complete(text):
        return 0
    if "{" not in text and "PATH:" not in text:
        return 0
    return configured - requested


class LocalReasoningModel:
    def __init__(self, model_id: str, *, max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

        self.torch = torch
        self.StoppingCriteria = StoppingCriteria
        self.StoppingCriteriaList = StoppingCriteriaList
        self.model_id = model_id
        self.max_new_tokens = max(64, min(int(max_new_tokens), MAX_ALLOWED_NEW_TOKENS))
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=False,
            torch_dtype="auto",
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    def _json_stopping_criteria(self, prompt_tokens: int):
        tokenizer = self.tokenizer
        base = self.StoppingCriteria

        class StopAfterBoundedOutput(base):
            def __call__(self, input_ids, scores, **kwargs):
                generated = tokenizer.decode(input_ids[0][prompt_tokens:], skip_special_tokens=True)
                return bounded_coding_output_complete(generated)

        return self.StoppingCriteriaList([StopAfterBoundedOutput()])

    def _generate(self, input_ids, *, max_new_tokens: int, prompt_tokens: int, **inputs):
        return self.model.generate(
            input_ids=input_ids,
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=1.03,
            pad_token_id=self.tokenizer.eos_token_id,
            stopping_criteria=self._json_stopping_criteria(prompt_tokens),
        )

    def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
        system = (
            "You are a replaceable reasoning provider for Genesis AI Network. "
            "You do not define Genesis identity. Give concise, testable, evidence-aware answers. "
            "Do not claim certainty where evidence is missing."
        )
        role = _prompt_role(prompt)
        initial_role_budget = role_token_budget(prompt)
        completion_role_budget = role_completion_budget(prompt)
        prompt = simplify_bounded_coding_prompt(prompt)
        prompt = compact_prompt(prompt)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        try:
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=4096)
        input_ids = inputs.pop("input_ids")
        prompt_tokens = input_ids.shape[-1]
        budget = self.max_new_tokens if max_new_tokens is None else max(64, min(int(max_new_tokens), MAX_ALLOWED_NEW_TOKENS))
        if initial_role_budget is not None:
            budget = min(budget, initial_role_budget)
        configured_completion_budget = self.max_new_tokens
        if completion_role_budget is not None:
            configured_completion_budget = min(configured_completion_budget, completion_role_budget)
        with self.torch.no_grad():
            output = self._generate(
                input_ids,
                max_new_tokens=budget,
                prompt_tokens=prompt_tokens,
                **inputs,
            )
            generated = output[0][prompt_tokens:]
            decoded = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
            reserve = json_completion_reserve_tokens(
                decoded,
                generated_tokens=int(generated.shape[-1]),
                requested_budget=budget,
                configured_budget=configured_completion_budget,
            )
            eos_token_id = self.tokenizer.eos_token_id
            ended_with_eos = bool(generated.shape[-1]) and eos_token_id is not None and int(generated[-1]) == int(eos_token_id)
            if reserve and not ended_with_eos:
                output = self._generate(
                    output,
                    max_new_tokens=reserve,
                    prompt_tokens=prompt_tokens,
                )
                generated = output[0][prompt_tokens:]
                decoded = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        if role == "bounded_coding_engineer":
            return normalize_bounded_coding_output(decoded)
        return decoded


class Handler(BaseHTTPRequestHandler):
    model: LocalReasoningModel | None = None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ready", "provider": "genesis-local-reasoning", "model": self.model.model_id if self.model else None, "max_new_tokens": self.model.max_new_tokens if self.model else None})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/reason":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            self._json(400, {"error": "prompt required"})
            return
        max_new_tokens = payload.get("max_new_tokens")
        role_budget = role_token_budget(prompt)
        if role_budget is not None:
            try:
                requested_budget = int(max_new_tokens) if max_new_tokens is not None else role_budget
            except (TypeError, ValueError):
                requested_budget = role_budget
            max_new_tokens = min(requested_budget, role_budget)
        try:
            response = (
                self.model.reason(prompt, max_new_tokens=max_new_tokens)
                if self.model
                else ""
            )
            self._json(200, {"response": response})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--max-new-tokens", type=int, default=int(os.environ.get("GENESIS_PROVIDER_MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS))))
    args = parser.parse_args()

    Handler.model = LocalReasoningModel(args.model, max_new_tokens=args.max_new_tokens)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"status": "ready", "provider": "genesis-local-reasoning", "model": args.model, "max_new_tokens": Handler.model.max_new_tokens}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

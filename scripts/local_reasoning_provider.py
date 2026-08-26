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


def compact_prompt(prompt: str) -> str:
    """Keep bounded instructions/objective and recent repository context."""
    if len(prompt) <= MAX_PROVIDER_PROMPT_CHARS:
        return prompt
    head = MAX_PROVIDER_PROMPT_CHARS // 2
    tail = MAX_PROVIDER_PROMPT_CHARS - head
    return prompt[:head] + "\n[...bounded context elided...]\n" + prompt[-tail:]


def role_token_budget(prompt: str) -> int | None:
    """Return a narrow initial output cap for roles that only need compact JSON decisions."""
    for line in prompt.splitlines()[:8]:
        if line.startswith("ROLE:"):
            role = line.split(":", 1)[1].strip()
            return ROLE_MAX_NEW_TOKENS.get(role)
    return None


def role_completion_budget(prompt: str) -> int | None:
    """Return the maximum total generation budget for latency-sensitive roles."""
    for line in prompt.splitlines()[:8]:
        if line.startswith("ROLE:"):
            role = line.split(":", 1)[1].strip()
            return ROLE_MAX_COMPLETION_TOKENS.get(role)
    return None


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


def json_completion_reserve_tokens(
    text: str,
    *,
    generated_tokens: int,
    requested_budget: int,
    configured_budget: int,
) -> int:
    """Return a bounded reserve only when JSON was cut off by the request cap.

    Coding roles intentionally start with a compact request budget. If the model
    actually consumes that whole budget and has begun, but not completed, a JSON
    object, allow it to use only the remaining configured provider budget. This
    recovers token-limit truncation without extending garbage, early-EOS output,
    or already-complete JSON, and never exceeds the provider's configured cap.
    """
    requested = max(0, int(requested_budget))
    configured = max(0, int(configured_budget))
    if configured <= requested or generated_tokens < requested:
        return 0
    if "{" not in text or balanced_json_object_complete(text):
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

        class StopAfterBalancedJSONObject(base):
            def __call__(self, input_ids, scores, **kwargs):
                generated = tokenizer.decode(input_ids[0][prompt_tokens:], skip_special_tokens=True)
                return balanced_json_object_complete(generated)

        return self.StoppingCriteriaList([StopAfterBalancedJSONObject()])

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
        initial_role_budget = role_token_budget(prompt)
        completion_role_budget = role_completion_budget(prompt)
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

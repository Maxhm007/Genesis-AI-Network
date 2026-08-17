from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODEL = "Qwen/Qwen3-0.6B"
DEFAULT_MAX_NEW_TOKENS = 512
MAX_ALLOWED_NEW_TOKENS = 768
MAX_PROVIDER_PROMPT_CHARS = 14_000


def compact_prompt(prompt: str) -> str:
    """Keep bounded instructions/objective and recent repository context."""
    if len(prompt) <= MAX_PROVIDER_PROMPT_CHARS:
        return prompt
    head = MAX_PROVIDER_PROMPT_CHARS // 2
    tail = MAX_PROVIDER_PROMPT_CHARS - head
    return prompt[:head] + "\n[...bounded context elided...]\n" + prompt[-tail:]


class LocalReasoningModel:
    def __init__(self, model_id: str, *, max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
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

    def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
        system = (
            "You are a replaceable reasoning provider for Genesis AI Network. "
            "You do not define Genesis identity. Give concise, testable, evidence-aware answers. "
            "Do not claim certainty where evidence is missing."
        )
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
        budget = self.max_new_tokens if max_new_tokens is None else max(64, min(int(max_new_tokens), MAX_ALLOWED_NEW_TOKENS))
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=budget,
                do_sample=False,
                repetition_penalty=1.03,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[-1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()


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
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--max-new-tokens", type=int, default=int(os.environ.get("GENESIS_PROVIDER_MAX_NEW_TOKENS", str(DEFAULT_MAX_NEW_TOKENS))))
    args = parser.parse_args()

    Handler.model = LocalReasoningModel(args.model, max_new_tokens=args.max_new_tokens)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"status": "ready", "provider": "genesis-local-reasoning", "model": args.model, "max_new_tokens": Handler.model.max_new_tokens}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

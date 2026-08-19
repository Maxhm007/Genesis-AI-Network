from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 2048
MAX_ALLOWED_TOKENS = 4096
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _bounded_tokens(value: object) -> int:
    try:
        return max(128, min(int(value), MAX_ALLOWED_TOKENS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TOKENS


class AnthropicReasoningClient:
    """Small dependency-free adapter from Claude Messages API to Genesis text reasoning."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        api_url: str = DEFAULT_API_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_MODEL
        self.api_url = api_url.strip() or DEFAULT_API_URL
        self.max_tokens = _bounded_tokens(max_tokens)
        self.timeout = max(5.0, min(float(timeout), 300.0))

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def reason(self, prompt: str) -> str:
        if not self.available():
            raise RuntimeError("Anthropic API key/model is not configured")
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("prompt required")
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "user-agent": "Genesis-AI-Network/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Anthropic request failed with HTTP {exc.code}: {detail}") from exc
        content = body.get("content")
        if not isinstance(content, list):
            raise RuntimeError("Anthropic response did not contain content blocks")
        text_parts = [
            str(block.get("text"))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        ]
        text = "\n".join(part for part in text_parts if part.strip()).strip()
        if not text:
            raise RuntimeError("Anthropic response contained no text")
        return text


class Handler(BaseHTTPRequestHandler):
    client: AnthropicReasoningClient | None = None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            ready = bool(self.client and self.client.available())
            self._json(
                200 if ready else 503,
                {
                    "status": "ready" if ready else "unavailable",
                    "provider": "anthropic-claude",
                    "model": self.client.model if self.client else None,
                },
            )
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
            response = self.client.reason(prompt) if self.client else ""
            self._json(200, {"response": response})
        except Exception as exc:
            self._json(502, {"error": str(exc)[:1000]})

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    Handler.client = AnthropicReasoningClient(
        os.environ.get("ANTHROPIC_API_KEY", ""),
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        api_url=os.environ.get("ANTHROPIC_API_URL", DEFAULT_API_URL),
        max_tokens=_bounded_tokens(os.environ.get("ANTHROPIC_MAX_TOKENS", DEFAULT_MAX_TOKENS)),
        timeout=float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "180")),
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"status": "ready", "provider": "anthropic-claude", "model": Handler.client.model}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

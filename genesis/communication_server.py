from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .communication import GenesisCommunicator


class GenesisCommunicationHandler(BaseHTTPRequestHandler):
    communicator: GenesisCommunicator
    auth_token: str = ""
    web_root: Path

    def _authorized(self) -> bool:
        if not type(self).auth_token:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {type(self).auth_token}"
        return hmac.compare_digest(supplied, expected)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_ui(self) -> None:
        path = type(self).web_root / "index.html"
        if not path.exists():
            self._json(404, {"error": "ui_not_found"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._serve_ui()
            return
        if self.path == "/health":
            self._json(200, {"status": "awake", "service": "genesis-communication"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path == "/v1/capabilities":
            self._json(200, type(self).communicator.capabilities.report())
            return
        if self.path == "/v1/modules":
            self._json(200, type(self).communicator.module_status())
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/message":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20000:
                self._json(413, {"error": "payload_too_large"})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = type(self).communicator.reply(
                str(payload.get("sender", "anonymous")),
                str(payload.get("message", "")),
            )
            self._json(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": type(exc).__name__})

    def log_message(self, format: str, *args) -> None:
        return


def serve(root: Path, host: str, port: int, auth_token: str = "") -> None:
    communicator = GenesisCommunicator(root)
    handler = type("GenesisBoundCommunicationHandler", (GenesisCommunicationHandler,), {})
    handler.communicator = communicator
    handler.auth_token = auth_token
    handler.web_root = root / "web"
    server = ThreadingHTTPServer((host, port), handler)
    print(
        json.dumps(
            {
                "status": "awake",
                "listen": f"http://{host}:{port}",
                "ui": f"http://{host}:{port}/",
                "modules": f"http://{host}:{port}/v1/modules",
            }
        ),
        flush=True,
    )
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Genesis communication server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    token = os.environ.get("GENESIS_COMM_TOKEN", "").strip()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise SystemExit("GENESIS_COMM_TOKEN is required when binding beyond loopback")
    serve(root, args.host, args.port, token)


if __name__ == "__main__":
    main()

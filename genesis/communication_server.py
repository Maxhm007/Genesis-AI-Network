from __future__ import annotations

import argparse
import hmac
import json
import os
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .application import ApplicationModule
from .communication import GenesisCommunicator
from .modules.task_queue import PersistentTaskQueue, VALID_STATES
from .scorecard import GenesisScorecard


class GenesisCommunicationHandler(BaseHTTPRequestHandler):
    communicator: GenesisCommunicator
    auth_token: str = ""
    web_root: Path
    root: Path

    def _authorized(self) -> bool:
        if not type(self).auth_token:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {type(self).auth_token}"
        return hmac.compare_digest(supplied, expected)

    def _is_loopback(self) -> bool:
        host = str(self.client_address[0])
        return host in {"127.0.0.1", "::1"} or host.startswith("127.")

    def _owner_authorized(self) -> bool:
        # Owner dashboard is safe-by-default on loopback. If a token is configured,
        # owner APIs require that token even locally. Remote access always requires it.
        if type(self).auth_token:
            return self._authorized()
        return self._is_loopback()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, filename: str) -> None:
        path = type(self).web_root / filename
        if not path.exists():
            self._json(404, {"error": "ui_not_found"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _owner_dashboard(self) -> dict:
        root = type(self).root
        runtime = root / "runtime"
        scorecard = GenesisScorecard(root, type(self).communicator.providers).report()
        queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
        tasks = queue.list(limit=1000)
        counts = {state: 0 for state in sorted(VALID_STATES)}
        for task in tasks:
            counts[task.state] = counts.get(task.state, 0) + 1
        active = [task for task in tasks if task.state not in {"complete", "failed"}]
        active.sort(key=lambda item: (-item.priority, item.created_at))
        module_status = type(self).communicator.module_status()
        applications = ApplicationModule(root).inspect()
        security = self._read_json(runtime / "security_report.json")
        memory = self._read_json(runtime / "memory_status.json")
        self_learning = self._read_json(runtime / "self_learning_status.json")
        capability_growth = self._read_json(runtime / "capability_growth.json")
        return {
            "owner_only": True,
            "access_mode": "token" if type(self).auth_token else "loopback-only",
            "scorecard": scorecard,
            "tasks": {
                "counts": counts,
                "open_count": len(active),
                "high_priority": [asdict(task) for task in active[:12]],
            },
            "modules": module_status.get("modules", []),
            "module_summary": {
                "architecture": module_status.get("architecture"),
                "module_count": module_status.get("module_count", 0),
                "active_module_count": module_status.get("active_module_count", 0),
                "candidate_changes": module_status.get("module_change_proposals", [])[:5],
            },
            "applications": applications,
            "security": security or {"status": "Unmeasured"},
            "memory": memory or {"status": "Unmeasured"},
            "self_learning": self_learning or {"status": "Unmeasured"},
            "capability_growth": capability_growth,
        }

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._serve_html("index.html")
            return
        if self.path in {"/owner", "/owner/", "/owner.html"}:
            try:
                result = type(self).communicator.reply(
                    str(payload.get("sender", "anonymous")),
                    str(payload.get("message", "")),
                )
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": type(exc).__name__})
                self._json(403, {"error": "owner_dashboard_requires_private_authenticated_access"})
                return
            self._serve_html("owner.html")
            return
        if self.path == "/health":
            self._json(200, {"status": "awake", "service": "genesis-communication"})
            return
        if self.path == "/v1/owner/dashboard":
            if not self._owner_authorized():
                self._json(401, {"error": "owner_authentication_required"})
                return
            self._json(200, self._owner_dashboard())
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
    handler.root = root
    server = ThreadingHTTPServer((host, port), handler)
    print(
        json.dumps(
            {
                "status": "awake",
                "listen": f"http://{host}:{port}",
                "ui": f"http://{host}:{port}/",
                "owner_dashboard": f"http://{host}:{port}/owner",
                "modules": f"http://{host}:{port}/v1/modules",
                "owner_access": "token" if auth_token else "loopback-only",
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

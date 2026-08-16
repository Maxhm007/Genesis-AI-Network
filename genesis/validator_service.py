from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .promotion import make_signed_vote


PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(path.read_text().strip()))
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_text(base64.b64encode(raw).decode("ascii"))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def public_key_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


class ValidatorEngine:
    def __init__(self, root: Path, validator_id: str, key_path: Path) -> None:
        self.root = root.resolve()
        self.validator_id = validator_id
        self.key = _load_or_create_key(key_path)
        self.public_key = public_key_b64(self.key)
        self.constitution_hash = _sha256(self.root / "GENESIS_CONSTITUTION.md")
        expected = json.loads((self.root / "GENESIS_BLOCK.json").read_text())["constitution"]["sha256"]
        if self.constitution_hash != expected:
            raise RuntimeError("validator refuses startup: Constitution mismatch")

    def _git(self, *args: str, check: bool = True):
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=check)

    def validate_commit(self, candidate_commit: str) -> tuple[str, str]:
        main = self._git("rev-parse", "main").stdout.strip()
        if self._git("merge-base", "--is-ancestor", main, candidate_commit, check=False).returncode != 0:
            return "reject", "candidate is not descended from main"
        changed = self._git("diff", "--name-only", f"{main}..{candidate_commit}").stdout.splitlines()
        if any(path in PROTECTED_PATHS for path in changed):
            return "reject", "candidate changes protected Genesis identity files"

        current = self._git("branch", "--show-current").stdout.strip()
        self._git("checkout", "--detach", candidate_commit)
        try:
            test = subprocess.run(
                [os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"],
                cwd=self.root,
                text=True,
                capture_output=True,
            )
        finally:
            self._git("checkout", current or "main")

        if test.returncode != 0:
            return "reject", "test suite failed"
        return "approve", "protected files unchanged and full tests passed"

    def vote(self, candidate_commit: str):
        decision, reason = self.validate_commit(candidate_commit)
        return make_signed_vote(self.key, self.validator_id, candidate_commit, decision, reason)

    def status(self) -> dict:
        return {
            "validator_id": self.validator_id,
            "status": "awake",
            "public_key_b64": self.public_key,
            "constitution_sha256": self.constitution_hash,
        }


class Handler(BaseHTTPRequestHandler):
    engine: ValidatorEngine | None = None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, type(self).engine.status())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/validate":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        commit = str(payload.get("candidate_commit", "")).strip()
        if not commit:
            self._json(400, {"error": "candidate_commit required"})
            return
        try:
            vote = type(self).engine.vote(commit)
            self._json(200, asdict(vote))
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        return


def serve(root: Path, validator_id: str, key_path: Path, host: str, port: int) -> None:
    engine = ValidatorEngine(root, validator_id, key_path)
    handler = type(f"{validator_id}Handler", (Handler,), {})
    handler.engine = engine
    server = ThreadingHTTPServer((host, port), handler)
    print(json.dumps({"event": "validator_started", **engine.status(), "host": host, "port": port}), flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator-id", required=True)
    parser.add_argument("--key-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    serve(Path(__file__).resolve().parents[1], args.validator_id, Path(args.key_path), args.host, args.port)


if __name__ == "__main__":
    main()

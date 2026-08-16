from __future__ import annotations

import hashlib
import json
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit


MAX_PEER_STATUS_BYTES = 64 * 1024
MAX_CHALLENGE_CHARS = 128


@dataclass(frozen=True)
class PeerRecord:
    node_id: str
    url: str
    constitution_sha256: str
    last_seen: str
    status: str


class PeerStore:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS peers(
            node_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            constitution_sha256 TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            status TEXT NOT NULL
        )""")
        self.conn.commit()

    def upsert(self, record: PeerRecord) -> None:
        self.conn.execute("""
        INSERT INTO peers(node_id,url,constitution_sha256,last_seen,status)
        VALUES(?,?,?,?,?)
        ON CONFLICT(node_id) DO UPDATE SET
          url=excluded.url,
          constitution_sha256=excluded.constitution_sha256,
          last_seen=excluded.last_seen,
          status=excluded.status
        """, (record.node_id, record.url, record.constitution_sha256, record.last_seen, record.status))
        self.conn.commit()

    def list(self) -> list[PeerRecord]:
        rows = self.conn.execute("SELECT node_id,url,constitution_sha256,last_seen,status FROM peers ORDER BY node_id").fetchall()
        return [PeerRecord(*row) for row in rows]


def _read_bounded_json_response(response, max_bytes: int = MAX_PEER_STATUS_BYTES) -> dict:
    length_header = response.headers.get("Content-Length")
    if length_header:
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("invalid peer Content-Length") from exc
        if length < 0 or length > max_bytes:
            raise ValueError("peer response too large")
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("peer response too large")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("peer response must be a JSON object")
    return payload


class PeerClient:
    """Legacy V0.1 Constitution-hash probe retained for compatibility."""

    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout

    def probe(self, url: str, expected_constitution_hash: str) -> PeerRecord:
        endpoint = url.rstrip("/") + "/genesis/status"
        req = urllib.request.Request(endpoint, headers={"User-Agent": "Genesis-AI-Network/0.1"})
        now = datetime.now(timezone.utc).isoformat()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = _read_bounded_json_response(response)
            remote_hash = str(payload.get("constitution_sha256", ""))
            status = "compatible" if remote_hash == expected_constitution_hash else "constitution_mismatch"
            return PeerRecord(str(payload.get("node_id", url)), url, remote_hash, now, status)
        except Exception:
            return PeerRecord(hashlib.sha256(url.encode()).hexdigest()[:16], url, "", now, "offline")


class _StatusHandler(BaseHTTPRequestHandler):
    status_factory: Callable[[], dict] = lambda: {}
    handshake_factory: Callable[[str | None], dict] | None = None

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/genesis/status":
            self._json(type(self).status_factory())
            return
        if parsed.path == "/genesis/handshake" and type(self).handshake_factory is not None:
            challenge_values = parse_qs(parsed.query, keep_blank_values=True).get("challenge", [])
            challenge = challenge_values[0] if challenge_values else None
            if challenge is not None and (not challenge or len(challenge) > MAX_CHALLENGE_CHARS):
                self.send_response(400)
                self.end_headers()
                return
            self._json(type(self).handshake_factory(challenge))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


class PeerStatusServer:
    """Read-only peer endpoint supporting legacy status and nonce-bound GDEN handshake."""

    def __init__(
        self,
        host: str,
        port: int,
        status_factory: Callable[[], dict],
        handshake_factory: Callable[[str | None], dict] | None = None,
    ) -> None:
        handler = type("GenesisStatusHandler", (_StatusHandler,), {})
        handler.status_factory = staticmethod(status_factory)
        handler.handshake_factory = staticmethod(handshake_factory) if handshake_factory is not None else None
        self.server = ThreadingHTTPServer((host, port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def address(self) -> tuple[str, int]:
        return self.server.server_address

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

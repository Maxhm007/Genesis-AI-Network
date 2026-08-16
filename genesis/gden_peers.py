from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from .gden import verify_advertisement


MAX_HANDSHAKE_BYTES = 64 * 1024


@dataclass(frozen=True)
class AuthenticatedPeer:
    node_id: str
    url: str
    status: str
    constitution_sha256: str
    protocol_version: str
    capabilities: tuple[str, ...]
    contribution_policy: dict[str, Any]
    state_root: str
    public_key: str
    last_seen: str


def _read_bounded_json(response, max_bytes: int = MAX_HANDSHAKE_BYTES) -> dict:
    length_header = response.headers.get("Content-Length")
    if length_header:
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("invalid peer Content-Length") from exc
        if length < 0 or length > max_bytes:
            raise ValueError("peer handshake too large")
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("peer handshake too large")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("peer handshake must be a JSON object")
    return payload


class GDENPeerClient:
    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout

    def probe(self, url: str, expected_constitution_hash: str) -> AuthenticatedPeer:
        challenge = os.urandom(32).hex()
        endpoint = url.rstrip("/") + "/genesis/handshake?" + urlencode({"challenge": challenge})
        request = urllib.request.Request(endpoint, headers={"User-Agent": "Genesis-GDEN/0.1"})
        now = datetime.now(timezone.utc).isoformat()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                envelope = _read_bounded_json(response)
        except Exception:
            return AuthenticatedPeer("", url, "offline", "", "", (), {}, "", "", now)

        valid, status = verify_advertisement(
            envelope,
            expected_constitution_hash,
            expected_nonce=challenge,
        )
        payload = envelope.get("advertisement", {}) if isinstance(envelope, dict) else {}
        if not valid:
            return AuthenticatedPeer(
                str(payload.get("node_id", "")),
                url,
                status,
                str(payload.get("constitution_sha256", "")),
                str(payload.get("protocol_version", "")),
                tuple(payload.get("capabilities", []) or []),
                dict(payload.get("contribution_policy", {}) or {}),
                str(payload.get("state_root", "")),
                str(payload.get("public_key", "")),
                now,
            )
        return AuthenticatedPeer(
            str(payload["node_id"]),
            url,
            "authenticated",
            str(payload["constitution_sha256"]),
            str(payload["protocol_version"]),
            tuple(payload.get("capabilities", []) or []),
            dict(payload.get("contribution_policy", {}) or {}),
            str(payload.get("state_root", "")),
            str(payload.get("public_key", "")),
            now,
        )

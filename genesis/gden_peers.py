from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .gden import verify_advertisement


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


class GDENPeerClient:
    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout

    def probe(self, url: str, expected_constitution_hash: str) -> AuthenticatedPeer:
        endpoint = url.rstrip("/") + "/genesis/handshake"
        request = urllib.request.Request(endpoint, headers={"User-Agent": "Genesis-GDEN/0.1"})
        now = datetime.now(timezone.utc).isoformat()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except Exception:
            return AuthenticatedPeer("", url, "offline", "", "", (), {}, "", "", now)

        valid, status = verify_advertisement(envelope, expected_constitution_hash)
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

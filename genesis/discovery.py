from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveryResult:
    source: str
    ok: bool
    items: list[dict]
    error: str | None = None


class DiscoveryEngine:
    """Read-only discovery of configured public JSON endpoints.

    Discovery never downloads or executes model code. Returned items are only
    candidate metadata for later license/security/benchmark review.
    """

    def __init__(self, root: Path, timeout: float = 8.0) -> None:
        self.root = root
        self.timeout = timeout
        self.config_path = root / "config" / "discovery_sources.json"

    def sources(self) -> list[dict]:
        if not self.config_path.exists():
            return []
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return [item for item in data.get("sources", []) if item.get("enabled", False)]

    def scan(self) -> list[DiscoveryResult]:
        results: list[DiscoveryResult] = []
        for source in self.sources():
            name = source["name"]
            url = source["url"]
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Genesis-AI-Network/0.1"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, list):
                    items = payload[: int(source.get("max_items", 10))]
                else:
                    items = [payload]
                results.append(DiscoveryResult(name, True, items))
            except Exception as exc:
                results.append(DiscoveryResult(name, False, [], str(exc)))
        return results

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue


class CompetitiveReferenceMonitor:
    """Watch official frontier-evaluation sources for staleness or change.

    Genesis never rewrites benchmark targets directly from unreviewed web text.
    A changed/stale source creates a persistent refresh task that must pass the
    normal research/review/update path.
    """

    def __init__(self, root: Path, timeout: float = 15.0) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self.config_path = self.root / "config" / "competitive_ai_reference.json"
        self.state_path = self.root / "runtime" / "competitive_reference_state.json"
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    @staticmethod
    def _sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _is_stale(self, config: dict) -> bool:
        stamp = datetime.fromisoformat(str(config["as_of"])).replace(tzinfo=timezone.utc)
        max_days = int(config.get("refresh_after_days", 30))
        return (datetime.now(timezone.utc) - stamp).days >= max_days

    def check(self) -> dict:
        if not self.config_path.exists():
            return {"status": "missing_reference"}
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        previous = {}
        if self.state_path.exists():
            try:
                previous = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                previous = {}
        sources: list[dict] = []
        changed = False
        errors: list[dict] = []
        old_hashes = {item.get("url"): item.get("sha256") for item in previous.get("sources", [])}
        for source in config.get("reference_sources", []):
            url = str(source.get("url", ""))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Genesis-AI-Network/0.3"})
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    body = response.read()
                digest = self._sha(body)
                sources.append({"name": source.get("name"), "url": url, "sha256": digest})
                if old_hashes.get(url) not in {None, digest}:
                    changed = True
            except Exception as exc:
                try:
                    raise Exception('This is a test exception')
                except Exception as exc:
                    errors.append({"url": url, "error": str(exc)})
        stale = self._is_stale(config)
        task_created = False
        if changed or stale:
            reason = "source_changed" if changed else "reference_stale"
            _, task_created = self.queue.create_unique(
                "competitive-reference-refresh:" + str(config.get("as_of")),
                "Refresh Genesis competitive AI benchmark reference from current official frontier evaluation disclosures.",
                module_id="genesis.capability",
                priority=95,
                payload={
                    "task_type": "competitive_reference_refresh",
                    "reason": reason,
                    "current_reference_as_of": config.get("as_of"),
                    "sources": config.get("reference_sources", []),
                    "rule": "Do not change benchmark targets without provenance and review.",
                },
            )
        state = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "reference_as_of": config.get("as_of"),
            "stale": stale,
            "source_changed": changed,
            "sources": sources,
            "errors": errors,
            "refresh_task_created": task_created,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state

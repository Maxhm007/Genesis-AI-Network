from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .discovery import DiscoveryEngine
from .evolution import EvolutionManager
from .knowledge import KnowledgeStore
from .providers import ProviderRegistry


class GenesisNode:
    def __init__(self, root: Path, db_path: Path | None = None, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.constitution_path = self.root / "GENESIS_CONSTITUTION.md"
        self.genesis_block_path = self.root / "GENESIS_BLOCK.json"
        self.db_path = db_path or (self.root / "state" / "genesis.db")
        self.providers = providers or ProviderRegistry()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            event TEXT NOT NULL, payload TEXT NOT NULL, event_hash TEXT NOT NULL)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS node_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        self.conn.commit()
        self.knowledge = KnowledgeStore(self.conn)
        self.evolution = EvolutionManager(self.root, self.conn)
        self.discovery = DiscoveryEngine(self.root)
        self._bootstrap_candidate_created = False

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def verify_constitution(self) -> str:
        constitution = self.constitution_path.read_bytes()
        block = json.loads(self.genesis_block_path.read_text(encoding="utf-8"))
        expected = block["constitution"]["sha256"]
        actual = self._sha256(constitution)
        if actual != expected:
            raise RuntimeError(f"Genesis Constitution verification failed: expected {expected}, got {actual}")
        self.audit("constitution_verified", {"sha256": actual})
        return actual

    def audit(self, event: str, payload: dict) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        event_hash = self._sha256(f"{created_at}|{event}|{payload_text}".encode("utf-8"))
        self.conn.execute(
            "INSERT INTO audit_log(created_at,event,payload,event_hash) VALUES(?,?,?,?)",
            (created_at, event, payload_text, event_hash),
        )
        self.conn.commit()
        return event_hash

    def set_state(self, key: str, value: str) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""INSERT INTO node_state(key,value,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, updated_at))
        self.conn.commit()

    def refresh_operating_mode(self) -> str:
        statuses = self.providers.statuses()
        available = [status.name for status in statuses if status.available]
        mode = "active" if available else "maintenance"
        self.set_state("operating_mode", mode)
        self.set_state("available_providers", json.dumps(available, sort_keys=True))
        self.audit("provider_discovery", {"mode": mode, "providers": [
            {"name": s.name, "available": s.available} for s in statuses]})
        return mode

    def discovery_cycle(self) -> None:
        results = self.discovery.scan()
        discovered = 0
        for result in results:
            self.audit("discovery_source", {
                "source": result.source, "ok": result.ok,
                "items": len(result.items), "error": result.error})
            if not result.ok:
                continue
            for item in result.items:
                name = str(item.get("id") or item.get("name") or item.get("modelId") or "unknown")
                digest = self.knowledge.add_candidate(
                    claim=f"Public model candidate discovered: {name}",
                    source=result.source,
                    source_type="model_registry",
                    evidence_level="metadata-only",
                    metadata={"item": item},
                )
                discovered += 1
                self.audit("knowledge_candidate_added", {"hash": digest, "source": result.source})
        self.set_state("last_discovery_count", str(discovered))

    def evolution_cycle(self) -> None:
        if self._bootstrap_candidate_created:
            return
        candidate_id = self.evolution.propose(
            "Add multi-node peer discovery",
            "Genesis currently has only single-node persistence. Multi-node discovery is required before network-level continuity can exist.",
            {"scope": "future", "required_tests": ["peer identity", "signed handshake", "state reconciliation"]},
        )
        valid = self.evolution.validate_structure(candidate_id)
        self.audit("evolution_candidate_created", {"id": candidate_id, "structurally_valid": valid, "promoted": False})
        self._bootstrap_candidate_created = True

    def heartbeat(self, cycle: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        mode = self.refresh_operating_mode()
        self.set_state("last_heartbeat", now)
        self.set_state("cycle", str(cycle))
        self.audit("heartbeat", {"cycle": cycle, "at": now, "mode": mode})
        print(f"[{now}] Genesis Node awake — cycle {cycle} — mode={mode}", flush=True)

    def maintenance_cycle(self, cycle: int) -> None:
        self.heartbeat(cycle)
        self.discovery_cycle()
        self.evolution_cycle()
        self.audit("maintenance_cycle_completed", {
            "cycle": cycle,
            "knowledge": self.knowledge.counts(),
            "evolution": self.evolution.status_counts(),
        })

    def run(self, interval_seconds: float = 5.0, cycles: int | None = None) -> None:
        constitution_hash = self.verify_constitution()
        print("Genesis Constitution verified:", constitution_hash, flush=True)
        print("Genesis Node V0.1 is awake.", flush=True)
        self.audit("node_started", {"version": "0.1.0"})
        cycle = 0
        try:
            while cycles is None or cycle < cycles:
                cycle += 1
                self.maintenance_cycle(cycle)
                if cycles is None or cycle < cycles:
                    time.sleep(interval_seconds)
        finally:
            self.audit("node_stopped", {"last_cycle": cycle})
            self.conn.close()

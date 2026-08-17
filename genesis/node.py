from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .discovery import DiscoveryEngine
from .evolution import EvolutionManager
from .identity import GeneIdentity
from .knowledge import KnowledgeStore
from .models import ModelEvaluator
from .peers import PeerClient, PeerStore
from .providers import ProviderRegistry
from .research import ResearchEngine
from .team import AITeam


class GenesisNode:
    def __init__(self, root: Path, db_path: Path | None = None, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.constitution_path = self.root / "GENESIS_CONSTITUTION.md"
        self.genesis_block_path = self.root / "GENESIS_BLOCK.json"
        self.db_path = db_path or (self.root / "state" / "genesis.db")
        self.providers = providers or ProviderRegistry()
        self.identity = GeneIdentity.load(self.root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event TEXT NOT NULL,
            payload TEXT NOT NULL,
            event_hash TEXT NOT NULL)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS node_state(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        self.conn.commit()
        self.knowledge = KnowledgeStore(self.conn)
        self.evolution = EvolutionManager(self.root, self.conn)
        self.discovery = DiscoveryEngine(self.root)
        self.model_evaluator = ModelEvaluator()
        self.research = ResearchEngine()
        self.team = AITeam(self.providers)
        self.peers = PeerStore(self.conn)
        self.peer_client = PeerClient()

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def verify_constitution(self) -> str:
        actual = self._sha256(self.constitution_path.read_bytes())
        block = json.loads(self.genesis_block_path.read_text(encoding="utf-8"))
        expected = block["constitution"]["sha256"]
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
        self.conn.execute("""
        INSERT INTO node_state(key,value,updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
        """, (key, value, updated_at))
        self.conn.commit()

    def refresh_operating_mode(self) -> str:
        statuses = self.providers.statuses()
        available = [s.name for s in statuses if s.available]
        mode = "active" if available else "maintenance"
        self.set_state("operating_mode", mode)
        self.set_state("available_providers", json.dumps(available, sort_keys=True))
        self.set_state("gene_nickname", self.identity.nickname)
        self.set_state("gene_plan", json.dumps(list(self.identity.system_plan), sort_keys=True))
        self.audit("provider_discovery", {
            "mode": mode,
            "providers": [{"name": s.name, "available": s.available} for s in statuses],
        })
        return mode

    def discovery_cycle(self) -> dict:
        found = 0
        review_candidates = 0
        failures = []
        for result in self.discovery.scan():
            if not result.ok:
                failures.append({"source": result.source, "error": result.error})
                continue
            for item in result.items:
                assessment = self.model_evaluator.assess(item)
                self.knowledge.add_candidate(
                    claim=f"Discovered AI model {assessment.model_id}: {assessment.status}, score={assessment.score}",
                    source=result.source,
                    source_type="model_registry",
                    evidence_level="metadata-only",
                    metadata={
                        "model_id": assessment.model_id,
                        "assessment_status": assessment.status,
                        "score": assessment.score,
                        "reasons": assessment.reasons,
                        "license": assessment.license,
                        "downloads": assessment.downloads,
                        "likes": assessment.likes,
                    },
                )
                found += 1
                if assessment.status == "review_candidate":
                    review_candidates += 1
        summary = {"models_seen": found, "review_candidates": review_candidates, "failures": failures}
        self.audit("model_discovery_cycle", summary)
        return summary

    def research_cycle(self, limit: int = 3) -> dict:
        added = 0
        errors: list[str] = []
        try:
            items = self.research.longevity_scan(limit=limit)
            for item in items:
                self.knowledge.add_candidate(
                    claim=item.title,
                    source=item.url,
                    source_type="scientific_literature",
                    evidence_level="unreviewed-publication-metadata",
                    metadata={"provider": item.source, "published": item.published, "summary": item.summary},
                )
                added += 1
        except Exception as exc:
            errors.append(str(exc))
        summary = {"research_items_added": added, "errors": errors}
        self.audit("research_cycle", summary)
        return summary

    def team_cycle(self, mode: str) -> dict:
        objective = (
            "Advance scientifically supported physical human immortality while following Gene's self-development and "
            "Master-AI coordination plan. Review current candidate knowledge and propose the smallest safe next research "
            "or engineering step."
        )
        outputs = self.team.run_task(
            objective,
            context=(
                f"operating_mode={mode}; knowledge={self.knowledge.counts()}\n"
                + self.identity.context_text()
            ),
        )
        completed = 0
        waiting = 0
        for output in outputs:
            if output.get("status") == "completed":
                completed += 1
                self.knowledge.add_candidate(
                    claim=str(output.get("output", ""))[:12000],
                    source=f"agent:{output['agent']}:{output.get('provider','unknown')}",
                    source_type="ai_team_output",
                    evidence_level="unreviewed-model-output",
                    metadata={"agent": output["agent"], "provider": output.get("provider")},
                )
            else:
                waiting += 1
        summary = {"roster": self.team.roster(), "completed": completed, "waiting": waiting}
        self.audit("ai_team_cycle", summary)
        return summary

    def evolution_cycle(self, research_summary: dict, discovery_summary: dict, team_summary: dict) -> str:
        candidate_id = self.evolution.propose(
            title="Improve Gene autonomy from latest cycle",
            rationale="Record a bounded candidate improvement based on observed research, model discovery, AI-team availability, and Gene's active plan.",
            changes={
                "research": research_summary,
                "model_discovery": discovery_summary,
                "ai_team": {"completed": team_summary["completed"], "waiting": team_summary["waiting"]},
                "gene_nickname": self.identity.nickname,
                "master_ai_objective": self.identity.master_ai_objective,
                "rule": "Candidate only; no automatic source-code replacement.",
            },
        )
        structural_ok = self.evolution.validate_structure(candidate_id)
        self.audit("evolution_candidate_created", {"candidate_id": candidate_id, "structural_ok": structural_ok})
        return candidate_id

    def probe_peer(self, url: str) -> dict:
        constitution_hash = self.verify_constitution()
        record = self.peer_client.probe(url, constitution_hash)
        self.peers.upsert(record)
        payload = {"node_id": record.node_id, "url": record.url, "status": record.status, "constitution_sha256": record.constitution_sha256}
        self.audit("peer_probe", payload)
        return payload

    def status_payload(self, node_id: str = "gene-node-1") -> dict:
        row = self.conn.execute("SELECT value FROM node_state WHERE key='operating_mode'").fetchone()
        return {
            "network": self.identity.canonical_name,
            "nickname": self.identity.nickname,
            "version": "0.2.0",
            "node_id": node_id,
            "constitution_sha256": self._sha256(self.constitution_path.read_bytes()),
            "operating_mode": row[0] if row else "unknown",
            "master_ai_objective": self.identity.master_ai_objective,
            "system_plan": list(self.identity.system_plan),
            "knowledge": self.knowledge.counts(),
            "evolution": self.evolution.status_counts(),
        }

    def heartbeat(self, cycle: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        mode = self.refresh_operating_mode()
        discovery_summary = self.discovery_cycle()
        research_summary = self.research_cycle()
        team_summary = self.team_cycle(mode)
        candidate_id = self.evolution_cycle(research_summary, discovery_summary, team_summary)
        self.set_state("last_heartbeat", now)
        self.set_state("cycle", str(cycle))
        self.set_state("last_candidate", candidate_id)
        self.audit("heartbeat", {
            "cycle": cycle, "at": now, "mode": mode,
            "research": research_summary,
            "model_discovery": discovery_summary,
            "team_completed": team_summary["completed"],
            "candidate_id": candidate_id,
        })
        print(
            f"[{now}] {self.identity.nickname} awake — cycle {cycle} — mode={mode} — "
            f"research={research_summary['research_items_added']} — "
            f"models={discovery_summary['models_seen']} — team={team_summary['completed']}",
            flush=True,
        )

    def run(self, interval_seconds: float = 300.0, cycles: int | None = None) -> None:
        constitution_hash = self.verify_constitution()
        print("Genesis Constitution verified:", constitution_hash, flush=True)
        print(f"{self.identity.nickname} ({self.identity.canonical_name}) is awake.", flush=True)
        self.audit("node_started", {
            "version": "0.2.0",
            "nickname": self.identity.nickname,
            "master_ai_objective": self.identity.master_ai_objective,
            "ai_team": self.team.roster(),
        })
        cycle = 0
        try:
            while cycles is None or cycle < cycles:
                cycle += 1
                self.heartbeat(cycle)
                if cycles is None or cycle < cycles:
                    time.sleep(interval_seconds)
        finally:
            self.audit("node_stopped", {"last_cycle": cycle})
            self.conn.close()

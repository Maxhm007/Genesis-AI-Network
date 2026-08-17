from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .team import AITeam


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LearningOutcome:
    outcome_id: int
    task_ref: str
    domain: str
    agent: str
    provider: str
    success: float
    quality: float
    evidence_weight: float
    source: str
    created_at: str


class OutcomeLearningStore:
    """Operational feedback store for agent/provider performance.

    This store does not validate factual lessons. It only aggregates bounded
    execution evidence so Genesis can prefer combinations that have performed
    better on similar work. Evidence is weighted and reversible.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_ref TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    success REAL NOT NULL,
                    quality REAL NOT NULL,
                    evidence_weight REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_ref, agent, provider, source)
                )
                """
            )

    def record(
        self,
        *,
        task_ref: str,
        domain: str,
        agent: str,
        provider: str,
        success: float,
        quality: float = 0.5,
        evidence_weight: float = 1.0,
        source: str,
    ) -> bool:
        values = (task_ref.strip(), domain.strip() or "general", agent.strip() or "unknown", provider.strip() or "unknown")
        if not values[0]:
            raise ValueError("task_ref is required")
        success = max(0.0, min(float(success), 1.0))
        quality = max(0.0, min(float(quality), 1.0))
        evidence_weight = max(0.05, min(float(evidence_weight), 10.0))
        try:
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO learning_outcomes(
                        task_ref, domain, agent, provider, success, quality,
                        evidence_weight, source, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (*values, success, quality, evidence_weight, source.strip() or "runtime", utc_now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def list(self, limit: int = 5000) -> list[LearningOutcome]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM learning_outcomes ORDER BY outcome_id DESC LIMIT ?",
                (max(0, int(limit)),),
            ).fetchall()
        return [LearningOutcome(**dict(row)) for row in rows]

    def provider_scores(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        items = self.list()
        if domain:
            scoped = [item for item in items if item.domain == domain]
            if scoped:
                items = scoped
        groups: dict[str, list[LearningOutcome]] = {}
        for item in items:
            groups.setdefault(item.provider, []).append(item)
        ranked: list[dict[str, Any]] = []
        for provider, rows in groups.items():
            total_weight = sum(row.evidence_weight for row in rows)
            if total_weight <= 0:
                continue
            success = sum(row.success * row.evidence_weight for row in rows) / total_weight
            quality = sum(row.quality * row.evidence_weight for row in rows) / total_weight
            # Mild Bayesian-style shrinkage keeps tiny samples from dominating.
            confidence = min(1.0, math.log1p(len(rows)) / math.log(10))
            score = ((0.65 * success) + (0.35 * quality)) * (0.6 + 0.4 * confidence)
            ranked.append(
                {
                    "provider": provider,
                    "score": round(score, 6),
                    "success": round(success, 6),
                    "quality": round(quality, 6),
                    "samples": len(rows),
                    "evidence_weight": round(total_weight, 3),
                }
            )
        ranked.sort(key=lambda row: (row["score"], row["samples"]), reverse=True)
        return ranked

    def agent_scores(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        items = self.list()
        if domain:
            scoped = [item for item in items if item.domain == domain]
            if scoped:
                items = scoped
        groups: dict[str, list[LearningOutcome]] = {}
        for item in items:
            groups.setdefault(item.agent, []).append(item)
        ranked: list[dict[str, Any]] = []
        for agent, rows in groups.items():
            total_weight = sum(row.evidence_weight for row in rows)
            if total_weight <= 0:
                continue
            success = sum(row.success * row.evidence_weight for row in rows) / total_weight
            quality = sum(row.quality * row.evidence_weight for row in rows) / total_weight
            score = (0.65 * success) + (0.35 * quality)
            ranked.append(
                {
                    "agent": agent,
                    "score": round(score, 6),
                    "success": round(success, 6),
                    "quality": round(quality, 6),
                    "samples": len(rows),
                    "evidence_weight": round(total_weight, 3),
                }
            )
        ranked.sort(key=lambda row: (row["score"], row["samples"]), reverse=True)
        return ranked


def classify_domain(text: str) -> str:
    value = text.lower()
    rules = (
        (("security", "vulnerability", "attack", "secret", "auth"), "security"),
        (("research", "paper", "study", "evidence", "aging", "longevity"), "research"),
        (("code", "fix", "bug", "repair", "implementation", "develop"), "engineering"),
        (("provider", "model", "reasoning", "benchmark"), "model"),
        (("peer", "network", "distributed", "consensus", "replication"), "network"),
        (("validate", "validation", "promotion", "candidate", "quorum"), "validation"),
        (("communication", "respond to user", "reply to"), "communication"),
    )
    for keywords, domain in rules:
        if any(keyword in value for keyword in keywords):
            return domain
    return "general"


def _extract_quality(payload: dict[str, Any]) -> tuple[float, float]:
    """Return (quality, evidence_weight) from explicit review signals only."""
    candidates: list[Any] = [
        payload.get("quality_score"),
        payload.get("score"),
        payload.get("evaluation_score"),
    ]
    validation = payload.get("validation")
    if isinstance(validation, dict):
        candidates.extend([validation.get("quality_score"), validation.get("score")])
    for value in candidates:
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric > 1.0 and numeric <= 100.0:
                numeric /= 100.0
            if 0.0 <= numeric <= 1.0:
                return numeric, 2.0
    explicit = payload.get("accepted")
    if isinstance(explicit, bool):
        return (1.0 if explicit else 0.0), 2.0
    status = str(payload.get("review_status") or payload.get("result") or "").lower()
    if status in {"pass", "passed", "approved", "accepted", "validated"}:
        return 1.0, 2.0
    if status in {"fail", "failed", "rejected"}:
        return 0.0, 2.0
    return 0.5, 1.0


class AdaptiveLearningEngine:
    """Ingest task outcomes and publish reversible operating preferences."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.store = OutcomeLearningStore(self.runtime / "adaptive_learning.sqlite3")
        self.preferences_path = self.runtime / "learning_preferences.json"

    def _ingest_outputs(self, *, task_ref: str, objective: str, outputs: Iterable[dict[str, Any]], source: str, review: dict[str, Any] | None = None) -> int:
        domain = classify_domain(objective)
        quality, weight = _extract_quality(review or {})
        added = 0
        for output in outputs:
            status = str(output.get("status", "")).lower()
            success = 1.0 if status == "completed" else 0.0
            if self.store.record(
                task_ref=task_ref,
                domain=domain,
                agent=str(output.get("agent") or "unknown"),
                provider=str(output.get("provider") or "unknown"),
                success=success,
                quality=quality,
                evidence_weight=weight,
                source=source,
            ):
                added += 1
        return added

    def ingest_runtime(self) -> int:
        added = 0
        dispatch = self.runtime / "ai_team_dispatch.json"
        if dispatch.is_file():
            payload = json.loads(dispatch.read_text(encoding="utf-8"))
            task_ref = str(payload.get("task_id") or "dispatch-current")
            objective = str(payload.get("objective") or payload.get("owner_module") or "general AI team task")
            added += self._ingest_outputs(task_ref=task_ref, objective=objective, outputs=payload.get("outputs", []), source="ai_team_dispatch")

        for dirname in ("task_reviews", "research_reviews"):
            folder = self.runtime / dirname
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                task = payload.get("task") or {}
                task_ref = str(task.get("task_id") or payload.get("task_id") or path.stem)
                objective = str(task.get("objective") or payload.get("objective") or "reviewed task")
                outputs = payload.get("team_outputs") or payload.get("outputs") or []
                added += self._ingest_outputs(
                    task_ref=task_ref,
                    objective=objective,
                    outputs=outputs,
                    source=f"review:{dirname}:{path.name}",
                    review=payload,
                )
        return added

    def publish_preferences(self) -> dict[str, Any]:
        domains = sorted({item.domain for item in self.store.list()})
        payload = {
            "created_at": utc_now(),
            "rule": (
                "Operational preferences are derived from measured outcomes only. "
                "They do not validate factual lessons, bypass Security, or authorize promotion."
            ),
            "overall": {
                "providers": self.store.provider_scores(),
                "agents": self.store.agent_scores(),
            },
            "domains": {
                domain: {
                    "providers": self.store.provider_scores(domain=domain),
                    "agents": self.store.agent_scores(domain=domain),
                }
                for domain in domains
            },
        }
        self.preferences_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def run_once(self) -> dict[str, Any]:
        added = self.ingest_runtime()
        preferences = self.publish_preferences()
        return {
            "created_at": preferences["created_at"],
            "new_outcomes": added,
            "total_outcomes": len(self.store.list()),
            "provider_rankings": len(preferences["overall"]["providers"]),
            "agent_rankings": len(preferences["overall"]["agents"]),
            "domains": sorted(preferences["domains"].keys()),
        }


class LearningAwareAITeam(AITeam):
    """AI Team that prefers historically stronger providers for the current domain."""

    def __init__(self, providers, *, preferences_path: Path, **kwargs: Any) -> None:
        super().__init__(providers, **kwargs)
        self.preferences_path = Path(preferences_path)
        self._current_domain = "general"

    def run_task(self, objective: str, context: str = "") -> list[dict]:
        self._current_domain = classify_domain(f"{objective}\n{context}")
        return super().run_task(objective, context)

    def _preferred_providers(self, available: list) -> list:
        available = super()._preferred_providers(available)
        if not self.preferences_path.is_file():
            return available
        try:
            payload = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            rows = payload.get("domains", {}).get(self._current_domain, {}).get("providers") or payload.get("overall", {}).get("providers", [])
            rank = {str(row.get("provider")): index for index, row in enumerate(rows)}
        except Exception:
            return available
        original = {getattr(provider, "name", ""): index for index, provider in enumerate(available)}
        return sorted(available, key=lambda provider: (rank.get(getattr(provider, "name", ""), 10_000), original.get(getattr(provider, "name", ""), 10_000)))

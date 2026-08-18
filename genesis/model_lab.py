from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


MODEL_STATES = ("planned", "training", "tested", "validated", "trusted", "active", "rejected")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelLineage:
    model_id: str
    name: str
    base_model: str
    method: str
    dataset_ref: str
    dataset_hash: str
    state: str
    benchmark_score: float | None
    resource_cost: float | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelLab:
    """Persistent, provider-neutral Genesis-owned model development registry.

    This module records training/fine-tuning/distillation lineage and evidence.
    It deliberately does not execute arbitrary training commands or activate a
    model by recommendation alone. Model execution remains delegated to bounded
    adapters and promotion requires measured evidence.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.db_path = self.root / "runtime" / "model_lab.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_lineage (
                    model_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    base_model TEXT NOT NULL,
                    method TEXT NOT NULL,
                    dataset_ref TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    benchmark_score REAL,
                    resource_cost REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _id(name: str, base_model: str, method: str, dataset_hash: str) -> str:
        raw = f"{name}\0{base_model}\0{method}\0{dataset_hash}"
        return "genesis-model-" + sha256_text(raw)[:20]

    def plan(
        self,
        *,
        name: str,
        base_model: str,
        method: str,
        dataset_ref: str,
        dataset_hash: str,
    ) -> ModelLineage:
        values = [name, base_model, method, dataset_ref, dataset_hash]
        if not all(str(value).strip() for value in values):
            raise ValueError("name, base_model, method, dataset_ref and dataset_hash are required")
        model_id = self._id(name.strip(), base_model.strip(), method.strip(), dataset_hash.strip())
        existing = self.get(model_id)
        if existing:
            return existing
        now = utc_now()
        item = ModelLineage(
            model_id=model_id,
            name=name.strip(),
            base_model=base_model.strip(),
            method=method.strip(),
            dataset_ref=dataset_ref.strip(),
            dataset_hash=dataset_hash.strip(),
            state="planned",
            benchmark_score=None,
            resource_cost=None,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO model_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.model_id, item.name, item.base_model, item.method,
                    item.dataset_ref, item.dataset_hash, item.state,
                    item.benchmark_score, item.resource_cost,
                    item.created_at, item.updated_at,
                ),
            )
        return item

    def get(self, model_id: str) -> ModelLineage | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM model_lineage WHERE model_id = ?", (model_id,)).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[ModelLineage]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM model_lineage ORDER BY created_at DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def add_evidence(self, model_id: str, evidence_type: str, payload: dict[str, Any]) -> None:
        if self.get(model_id) is None:
            raise KeyError(model_id)
        if not evidence_type.strip():
            raise ValueError("evidence_type is required")
        with self._connect() as db:
            db.execute(
                "INSERT INTO model_evidence(model_id, evidence_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (model_id, evidence_type.strip(), json.dumps(payload, sort_keys=True), utc_now()),
            )

    def evidence(self, model_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT evidence_type, payload_json, created_at FROM model_evidence WHERE model_id = ? ORDER BY id",
                (model_id,),
            ).fetchall()
        return [
            {
                "evidence_type": row["evidence_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def transition(
        self,
        model_id: str,
        new_state: str,
        *,
        benchmark_score: float | None = None,
        resource_cost: float | None = None,
    ) -> ModelLineage:
        current = self.get(model_id)
        if current is None:
            raise KeyError(model_id)
        if new_state not in MODEL_STATES:
            raise ValueError("unknown model state")
        if new_state == "rejected":
            allowed = current.state not in {"active", "rejected"}
        else:
            allowed = (
                current.state in MODEL_STATES[:-1]
                and MODEL_STATES.index(new_state) == MODEL_STATES.index(current.state) + 1
            )
        if not allowed:
            raise ValueError("model lifecycle transition is not allowed")
        score = current.benchmark_score if benchmark_score is None else float(benchmark_score)
        cost = current.resource_cost if resource_cost is None else float(resource_cost)
        if new_state in {"validated", "trusted", "active"}:
            if score is None:
                raise ValueError("validated-or-higher model requires benchmark evidence")
            if not any(row["evidence_type"] == "benchmark" for row in self.evidence(model_id)):
                raise ValueError("validated-or-higher model requires stored benchmark evidence")
        now = utc_now()
        with self._connect() as db:
            db.execute(
                "UPDATE model_lineage SET state = ?, benchmark_score = ?, resource_cost = ?, updated_at = ? WHERE model_id = ?",
                (new_state, score, cost, now, model_id),
            )
        updated = self.get(model_id)
        assert updated is not None
        return updated

    def export_status(self) -> dict[str, Any]:
        items = self.list()
        return {
            "module": "genesis.model_lab",
            "models": [item.as_dict() for item in items],
            "counts": {state: sum(1 for item in items if item.state == state) for state in MODEL_STATES},
            "rule": "Genesis-owned models remain replaceable capabilities and cannot self-promote without measured evidence.",
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ModelLineage:
        return ModelLineage(
            model_id=row["model_id"],
            name=row["name"],
            base_model=row["base_model"],
            method=row["method"],
            dataset_ref=row["dataset_ref"],
            dataset_hash=row["dataset_hash"],
            state=row["state"],
            benchmark_score=None if row["benchmark_score"] is None else float(row["benchmark_score"]),
            resource_cost=None if row["resource_cost"] is None else float(row["resource_cost"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

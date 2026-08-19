from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


GENESIS_PREFIXES = ("genesis", "gene", "selfdev", "proactive", "gaps")


@dataclass(frozen=True)
class AutonomyProofEvent:
    cycle_id: str
    stage: str
    actor: str
    classification: str
    outcome: str
    details: dict
    recorded_at: str

    def as_dict(self) -> dict:
        return asdict(self)


class AutonomyProofLedger:
    """Append-only evidence of who initiated and completed self-development.

    The ledger lives under ``runtime/task_reviews`` because that directory is
    already included in Genesis's durable GitHub Actions runtime cache. A
    legacy ``runtime/autonomy_proof.jsonl`` file is migrated once when present.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.proof_dir = self.runtime / "task_reviews"
        self.proof_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.proof_dir / "autonomy_proof.jsonl"
        legacy = self.runtime / "autonomy_proof.jsonl"
        if legacy.is_file() and not self.path.exists():
            self.path.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")

    @staticmethod
    def classify_actor(actor: str) -> str:
        value = (actor or "external").strip().lower()
        if value.startswith(GENESIS_PREFIXES):
            return "genesis_autonomous"
        if value in {"owner", "user", "human", "chatgpt", "external", "unknown"}:
            return "external"
        if "genesis" in value or "gene" in value:
            return "genesis_autonomous"
        return "assisted"

    def record(self, *, cycle_id: str, stage: str, actor: str, outcome: str, details: dict | None = None) -> dict:
        event = AutonomyProofEvent(
            cycle_id=cycle_id,
            stage=stage,
            actor=actor or "external",
            classification=self.classify_actor(actor),
            outcome=outcome,
            details=dict(details or {}),
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
        return event.as_dict()

    def events(self, limit: int = 200) -> list[dict]:
        if not self.path.is_file():
            return []
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def report(self, limit: int = 100) -> dict:
        rows = self.events(limit)
        completed = [row for row in rows if row.get("stage") == "cycle_complete"]
        autonomous = [row for row in completed if row.get("classification") == "genesis_autonomous"]
        assisted = [row for row in completed if row.get("classification") == "assisted"]
        external = [row for row in completed if row.get("classification") == "external"]
        total = len(completed)
        autonomous_ratio = (len(autonomous) / total) if total else 0.0
        return {
            "completed_cycles": total,
            "genesis_autonomous_cycles": len(autonomous),
            "assisted_cycles": len(assisted),
            "external_cycles": len(external),
            "autonomous_ratio": round(autonomous_ratio, 4),
            "proof_status": "proven" if total >= 5 and autonomous_ratio >= 0.8 else "collecting_evidence",
            "proof_path": str(self.path.relative_to(self.root)),
            "principle": "Autonomy is credited only when the ledger identifies Genesis as the initiator/completer; missing provenance receives no autonomous credit.",
        }

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.gene_continuous_work import run_step


@dataclass(frozen=True)
class PulseResult:
    logical_id: str
    action: str
    mode: str
    task_id: str | None
    needs_next_pulse: bool
    payload: dict


class GenePulse:
    """Execute one resumable unit of Gene work.

    A pulse is deliberately short-lived. Persistent state belongs to the Gene
    runtime/state backend, not to the process executing this class.
    """

    def __init__(self, root: Path, logical_id: str = "gene-node-1") -> None:
        self.root = Path(root).resolve()
        self.logical_id = logical_id

    def run(self) -> PulseResult:
        payload = run_step(self.logical_id)
        decision = dict(payload.get("decision", {}) or {})
        action = str(payload.get("action", "unknown"))
        mode = str(decision.get("mode", "unknown"))
        task_id = decision.get("task_id")

        # Gene is intentionally continuous: issue solving requests another pulse
        # until resolution, while discovery mode requests another pulse so Gene
        # can keep learning and looking for the next logical issue.
        needs_next = action not in {"fatal_stop", "owner_stop"}
        return PulseResult(
            logical_id=self.logical_id,
            action=action,
            mode=mode,
            task_id=str(task_id) if task_id else None,
            needs_next_pulse=needs_next,
            payload=payload,
        )

    def report(self) -> dict:
        return asdict(self.run())

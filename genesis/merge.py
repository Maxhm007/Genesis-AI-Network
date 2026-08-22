from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MERGE_MODULE_ID = "genesis.merge"
PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}


@dataclass(frozen=True)
class MergeEvidence:
    task_id: str
    candidate_sha: str
    target_path: str
    approved: bool
    reason: str
    recorded_at: str

    def as_dict(self) -> dict:
        return asdict(self)


class MergeModule:
    """Final promotion boundary for validated Genesis candidates.

    This submodule cannot create candidates or approve its own work. GitHub's
    independent candidate-promotion workflow retains the protected ref write and
    validator quorum. The Merge Module verifies that the exact reviewed candidate
    (or an equivalent safe rebase) is present on main and records the handoff before
    learning closes the task.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.events_path = self.root / "runtime" / "autonomy_pipeline" / "merge_events.jsonl"
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _history_has_review(record: Any) -> bool:
        for event in getattr(record, "history", ()) or ():
            if not isinstance(event, dict):
                continue
            if event.get("worker") == "review" and event.get("stage") == "validation_ready":
                return True
        return False

    @staticmethod
    def _history_has_promotion_observation(record: Any) -> bool:
        for event in getattr(record, "history", ()) or ():
            if not isinstance(event, dict):
                continue
            if event.get("worker") == "promotion" and event.get("stage") == "promoted":
                return True
        return False

    def candidate_present_on_main(self, candidate_sha: str) -> bool:
        if not candidate_sha:
            return False
        self._git("fetch", "origin", "main")
        direct = self._git("merge-base", "--is-ancestor", candidate_sha, "origin/main")
        if direct.returncode == 0:
            return True
        # Candidate Promotion may rebase a reviewed candidate onto a newer main;
        # git cherry recognizes patch-equivalent promotion when the SHA changes.
        cherry = self._git("cherry", "origin/main", candidate_sha)
        lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
        return bool(lines) and all(line.startswith("-") for line in lines)

    def verify(self, record: Any) -> MergeEvidence:
        task_id = str(getattr(record, "task_id", "") or "")
        candidate_sha = str(getattr(record, "candidate_sha", "") or "")
        target_path = str(getattr(record, "target_path", "") or "").replace("\\", "/").lstrip("./")

        approved = True
        reason = "validated_candidate_present_on_main"
        if str(getattr(record, "stage", "") or "") != "promoted":
            approved, reason = False, "pipeline_not_in_promoted_state"
        elif not candidate_sha:
            approved, reason = False, "candidate_sha_missing"
        elif target_path in PROTECTED_PATHS or target_path.startswith(".github/"):
            approved, reason = False, "normal_autonomous_merge_target_protected"
        elif not self._history_has_review(record):
            approved, reason = False, "internal_review_approval_missing"
        elif not self._history_has_promotion_observation(record):
            approved, reason = False, "independent_promotion_observation_missing"
        elif not self.candidate_present_on_main(candidate_sha):
            approved, reason = False, "candidate_not_present_on_main"

        return MergeEvidence(
            task_id=task_id,
            candidate_sha=candidate_sha,
            target_path=target_path,
            approved=approved,
            reason=reason,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )

    def record(self, evidence: MergeEvidence) -> dict:
        payload = evidence.as_dict()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return payload

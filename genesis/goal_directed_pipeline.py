from __future__ import annotations

import re
from typing import Any

from .bounded_autonomy_pipeline import BoundedAutonomyPipelineCoordinator


class GoalDirectedPipelineCoordinator(BoundedAutonomyPipelineCoordinator):
    """Bounded pipeline coordinator with a goal-selected task preference.

    Preference changes scheduling only. The selected record is still executed by
    the canonical triage/development/repair/review/validation/learning workers,
    so goal orchestration cannot bypass scope, review, validation, or promotion.
    Durable Genesis review work has higher priority than an unrelated preferred
    goal so a surviving autonomous candidate cannot be starved indefinitely.
    """

    _EXECUTABLE_STAGES = {
        "promoted",
        "review_ready",
        "needs_development_revision",
        "needs_repair",
        "development_ready",
        "repair_ready",
        "discovered",
        "validation_ready",
    }
    _STALE_LEARNING_STAGES = {
        "discovered",
        "development_ready",
        "needs_development_revision",
    }
    _MAX_UNKNOWN_RELEASE_FRAGMENT_CHARS = 240
    _RELEASE_PACKAGING_MARKERS = (
        "**Website:**",
        "**Attestations:**",
        "**macOS/iOS:**",
        "**Linux:**",
        "**Android:**",
        "**Windows:**",
        "### Assets",
    )

    def _run_record(self, record: Any) -> dict:
        stage = str(record.stage)
        if stage == "promoted":
            return {"handled": True, **self.learning.run(record)}
        if stage == "review_ready":
            return {"handled": True, **self.review.run(record)}
        if stage in {"needs_development_revision", "development_ready"}:
            return {"handled": True, **self.development.run(record)}
        if stage in {"needs_repair", "repair_ready"}:
            return {"handled": True, **self.repair.run(record)}
        if stage == "discovered":
            return {"handled": True, **self.triage.run(record)}
        if stage == "validation_ready":
            return {"handled": True, **self.validation.run(record)}
        return {"handled": False, "action": "goal_selected_stage_not_executable"}

    def _recover_orphan_review(self) -> dict | None:
        """Recover one strict Genesis-owned review before preferred-goal scheduling."""
        from .review_recovery import recover_one_orphan_review

        return recover_one_orphan_review(self.root, self)

    @staticmethod
    def _is_durable_review_ready(record: Any) -> bool:
        return bool(
            str(getattr(record, "stage", "")) == "review_ready"
            and str(getattr(record, "candidate_sha", "") or "")
            and str(getattr(record, "review_ref", "") or "").startswith("genesis/review-")
        )

    @classmethod
    def _release_technical_excerpt(cls, summary: object) -> str:
        text = str(summary or "")
        text = re.sub(r"<details[^>]*>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"</details>", " ", text, flags=re.IGNORECASE)
        positions = [
            text.find(marker)
            for marker in cls._RELEASE_PACKAGING_MARKERS
            if text.find(marker) >= 0
        ]
        if positions:
            text = text[: min(positions)]
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = re.sub(r"<https?://[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _is_stale_non_transferable_release_task(cls, task: Any, record: Any) -> bool:
        """Recognize only old queued items that the current intake policy would skip."""
        if str(getattr(record, "stage", "")) not in cls._STALE_LEARNING_STAGES:
            return False
        payload = dict(getattr(task, "payload", {}) or {})
        if str(payload.get("source") or "") != "genesis.evolution_learning":
            return False

        discovery = dict(payload.get("discovery") or {})
        finding = dict(discovery.get("finding") or {})
        if not finding:
            record_discovery = dict(getattr(record, "discovery", {}) or {})
            finding = dict(record_discovery.get("finding") or {})
        if not bool(finding.get("new_capability")):
            return False
        if str(finding.get("fallback_from") or "") != "no_existing_capability_domain":
            return False
        capability_domains = {
            str(value).strip()
            for value in (finding.get("capability_domains") or [])
            if str(value).strip()
        }
        if capability_domains != {"emerging_capability"}:
            return False

        learning = dict(payload.get("learning") or {})
        source = str(learning.get("source") or "").lower()
        url = str(learning.get("url") or "").lower()
        if not (source.startswith("github:") or "github.com/" in url):
            return False
        if "/releases/" not in url and "/releases/tag/" not in url:
            return False

        compact = cls._release_technical_excerpt(learning.get("summary"))
        if not compact or len(compact) > cls._MAX_UNKNOWN_RELEASE_FRAGMENT_CHARS:
            return False
        issue_or_pr = re.search(
            r"\(#\d+\)|\b(?:pr|issue)\s*#?\d+\b",
            compact,
            flags=re.IGNORECASE,
        )
        subsystem_prefix = re.match(r"^[A-Za-z0-9_.+/-]{2,24}\s*:\s+", compact)
        implementation_identifier = re.search(r"\b[A-Z][A-Z0-9]+_[A-Z0-9_]+\b", compact)
        release_like_title = re.fullmatch(
            r"(?:v?\d[\w.-]*|b\d+)",
            str(learning.get("title") or "").strip(),
            flags=re.IGNORECASE,
        )
        return bool(
            issue_or_pr
            or subsystem_prefix
            or implementation_identifier
            or release_like_title
        )

    def _retire_one_stale_learning_task(self) -> dict | None:
        """Stop one obsolete pre-development task before it consumes another coder call."""
        for record in sorted(
            self.store.list_active(),
            key=lambda item: (str(getattr(item, "updated_at", "")), str(item.task_id)),
        ):
            if str(getattr(record, "stage", "")) not in self._STALE_LEARNING_STAGES:
                continue
            task = self.engineering.queue.get(str(record.task_id))
            if task is None or not self._is_stale_non_transferable_release_task(task, record):
                continue

            reason = "release_fragment_not_transferable_policy"
            task_state = str(getattr(task, "state", ""))
            if task_state not in {"complete", "cancelled"}:
                task = self.engineering.queue.cancel(str(record.task_id), reason)
            updated = self.store.transition(
                str(record.task_id),
                "quarantined",
                worker="learning_policy",
                feedback=reason,
            )
            return {
                "handled": True,
                "action": "pipeline_learning_task_retired",
                "record": {
                    "task_id": str(updated.task_id),
                    "stage": str(updated.stage),
                    "last_feedback": str(getattr(updated, "last_feedback", "") or ""),
                },
                "task": {
                    "task_id": str(getattr(task, "task_id", record.task_id)),
                    "state": str(getattr(task, "state", task_state)),
                    "state_reason": str(getattr(task, "state_reason", "") or ""),
                },
                "retirement_reason": reason,
            }
        return None

    def _resume_existing_durable_review(self, preferred_task_id: str) -> dict | None:
        """Finish a represented review before scheduling unrelated goal work."""
        active = list(self.store.list_active())
        candidates = sorted(
            (record for record in active if self._is_durable_review_ready(record)),
            key=lambda record: (str(getattr(record, "updated_at", "")), str(record.task_id)),
        )
        if not candidates:
            return None
        record = candidates[0]
        result = self._run_record(record)
        result["goal_directed"] = False
        result["preferred_task_id"] = preferred_task_id or None
        result["durable_review_resumed"] = {
            "task_id": str(record.task_id),
            "candidate_sha": str(record.candidate_sha),
            "review_ref": str(record.review_ref),
        }
        return result

    def run_once(self, preferred_task_id: str | None = None) -> dict:
        preferred_task_id = str(preferred_task_id or "").strip()

        # Recovery may already have reconstructed this candidate in a prior Pulse.
        # In that case deduplication correctly prevents another reconstruction, but
        # the represented review still needs execution before unrelated preferred
        # work or it can remain stuck forever.
        resumed = self._resume_existing_durable_review(preferred_task_id)
        if resumed is not None:
            return resumed

        # If the durable Git ref has not yet been represented in runtime state,
        # reconstruct it and process its canonical review worker in the same Pulse.
        recovered = self._recover_orphan_review()
        if recovered:
            recovered_task_id = str(recovered.get("task_id") or "")
            recovered_record = self.store.get(recovered_task_id) if recovered_task_id else None
            if recovered_record is not None and str(recovered_record.stage) == "review_ready":
                result = self._run_record(recovered_record)
                result["goal_directed"] = False
                result["preferred_task_id"] = preferred_task_id or None
                result["orphan_review_recovery"] = recovered
                return result

        # Intake policy can become stricter after work was queued. Retire only old
        # pre-development release fragments here so they cannot burn another model
        # attempt. Review/validation/promoted work is deliberately outside this gate.
        retired = self._retire_one_stale_learning_task()
        if retired is not None:
            retired["goal_directed"] = False
            retired["preferred_task_id"] = preferred_task_id or None
            return retired

        if preferred_task_id:
            active = list(self.store.list_active())
            preferred = next(
                (
                    record
                    for record in active
                    if str(record.task_id) == preferred_task_id
                    and str(record.stage) in self._EXECUTABLE_STAGES
                ),
                None,
            )
            if preferred is not None:
                result = self._run_record(preferred)
                result["goal_directed"] = True
                result["preferred_task_id"] = preferred_task_id
                return result

        result = super().run_once()
        result["goal_directed"] = False
        result["preferred_task_id"] = preferred_task_id or None
        return result
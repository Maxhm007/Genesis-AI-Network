from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from .bounded_autonomy_pipeline import BoundedAutonomyPipelineCoordinator
from .improvement import IMPROVEMENT_MODULE_ID, ImprovementModule
from .merge import MERGE_MODULE_ID, MergeModule


class SingleAttemptImprovementWorker:
    """Improve one existing capability per Pulse without owning promotion."""

    MAX_FEEDBACK_BYTES = 4_000

    def __init__(self, root: Path, engineering, store) -> None:
        self.root = Path(root).resolve()
        self.engineering = engineering
        self.store = store
        self.module = ImprovementModule()

    @staticmethod
    def _normalize_path(path: object) -> str:
        return str(path).replace("\\", "/").lstrip("./")

    def run(self, record) -> dict:
        task = self.engineering.queue.get(record.task_id)
        if task is None:
            updated = self.store.transition(
                record.task_id,
                "quarantined",
                worker="improvement",
                feedback="task_missing",
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        if record.development_attempts >= task.max_attempts:
            updated = self.store.transition(
                record.task_id,
                "quarantined",
                worker="improvement",
                feedback="improvement_budget_exhausted",
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}

        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self.store.transition(record.task_id, "development_ready", worker="improvement")

        attempt_task = self.module.prepare_task(task, record)
        if record.last_feedback:
            attempt_task = replace(
                attempt_task,
                objective=(
                    attempt_task.objective
                    + "\n\nPREVIOUS_IMPROVEMENT_FEEDBACK: The previous bounded improvement did not pass. "
                    "Revise the SAME measured capability gap, change strategy when the evidence demands it, "
                    "and do not broaden scope.\n"
                    + record.last_feedback[-self.MAX_FEEDBACK_BYTES :]
                ),
            )

        old_revision_budget = self.engineering.MAX_CANDIDATE_REVISIONS
        self.engineering.MAX_CANDIDATE_REVISIONS = 0
        try:
            attempt = self.engineering._attempt_task(attempt_task, runtime)
        finally:
            self.engineering.MAX_CANDIDATE_REVISIONS = old_revision_budget

        if attempt.get("coding_status") == "waiting_for_coding_provider":
            feedback = str(
                attempt.get("error") or "waiting_for_non_qwen_coding_provider"
            )[-self.MAX_FEEDBACK_BYTES :]
            updated = self.store.transition(
                record.task_id,
                "needs_development_revision",
                worker="improvement",
                feedback=feedback,
            )
            return {
                "action": "pipeline_wait_development_provider",
                "specialist": IMPROVEMENT_MODULE_ID,
                "attempt": attempt,
                "record": asdict(updated),
            }

        candidate = dict(attempt.get("candidate") or {})
        security = dict(attempt.get("candidate_security") or {})
        candidate_ready = bool(
            attempt.get("coding_status") == "candidate_created"
            and candidate.get("committed")
            and candidate.get("commit_sha")
            and candidate.get("branch")
            and security.get("status") == "pass"
        )
        scope_error = ""
        if candidate_ready:
            expected_target = self._normalize_path(record.target_path)
            changed_files = tuple(
                self._normalize_path(path) for path in (candidate.get("changed_files") or ())
            )
            if len(changed_files) != 1 or changed_files[0] != expected_target:
                scope_error = (
                    "improvement_scope_violation: existing-capability improvement must change exactly "
                    f"the approved target {expected_target}; candidate changed {list(changed_files)}"
                )
                attempt["coding_status"] = "candidate_rejected_by_scope"
                attempt["error"] = scope_error

        if candidate_ready and not scope_error:
            candidate_sha = str(candidate["commit_sha"])
            branch = str(candidate["branch"])
            review_ref = f"genesis/review-{candidate_sha[:12]}"
            updated = self.store.transition(
                record.task_id,
                "review_ready",
                worker="improvement",
                candidate_branch=branch,
                candidate_sha=candidate_sha,
                review_ref=review_ref,
                bump_development=True,
            )
            # Keep the established action contract so gene-pulse.yml pushes the
            # exact candidate into the same independent review queue.
            return {
                "action": "pipeline_development_completed",
                "specialist": IMPROVEMENT_MODULE_ID,
                "attempt": attempt,
                "record": asdict(updated),
                "review_candidate": {
                    "branch": branch,
                    "candidate_sha": candidate_sha,
                    "review_ref": review_ref,
                },
            }

        candidate_message = str(candidate.get("message") or "").strip()
        feedback = str(
            attempt.get("error")
            or candidate_message
            or attempt.get("coding_status")
            or "improvement_attempt_failed"
        )[-self.MAX_FEEDBACK_BYTES :]
        current = self.engineering.queue.get(record.task_id)
        if current and current.state == "review":
            try:
                current = self.engineering.queue.transition(
                    current.task_id, "running", module_id=IMPROVEMENT_MODULE_ID
                )
            except Exception:
                current = self.engineering.queue.get(record.task_id)
        if current and current.state not in {"failed", "quarantined", "complete"}:
            try:
                current = self.engineering.queue.record_failure(
                    current.task_id,
                    feedback,
                    classification="pipeline_improvement",
                    retry_after_seconds=0,
                    module_id=IMPROVEMENT_MODULE_ID,
                )
            except Exception:
                current = self.engineering.queue.get(record.task_id)
        terminal = bool(current and current.state == "quarantined")
        updated = self.store.transition(
            record.task_id,
            "quarantined" if terminal else "needs_development_revision",
            worker="improvement",
            feedback=feedback,
            bump_development=True,
        )
        return {
            "action": "pipeline_quarantined" if terminal else "pipeline_development_retry",
            "specialist": IMPROVEMENT_MODULE_ID,
            "attempt": attempt,
            "record": asdict(updated),
        }


class MergeWorker:
    """Record the validated merge boundary before learning closes a task."""

    def __init__(self, root: Path, engineering, store) -> None:
        self.root = Path(root).resolve()
        self.engineering = engineering
        self.store = store
        self.module = MergeModule(self.root)

    def run(self, record) -> dict:
        evidence = self.module.verify(record)
        self.module.record(evidence)
        if not evidence.approved:
            updated = self.store.transition(
                record.task_id,
                "quarantined",
                worker="merge",
                feedback=evidence.reason,
            )
            return {
                "action": "pipeline_quarantined",
                "specialist": MERGE_MODULE_ID,
                "merge_evidence": evidence.as_dict(),
                "record": asdict(updated),
            }
        updated = self.store.transition(
            record.task_id,
            "promoted",
            worker="merge",
            feedback=evidence.reason,
        )
        return {
            "action": "pipeline_merge_verified",
            "specialist": MERGE_MODULE_ID,
            "merge_evidence": evidence.as_dict(),
            "record": asdict(updated),
        }


def _last_worker(record) -> str:
    history = list(getattr(record, "history", ()) or ())
    if not history:
        return ""
    last = history[-1]
    return str(last.get("worker") or "") if isinstance(last, dict) else ""


def _patched_init(self, root: Path, engineering=None) -> None:
    original = type(self)._genesis_improvement_merge_original_init
    original(self, root, engineering)
    self.improvement = SingleAttemptImprovementWorker(self.root, self.engineering, self.store)
    self.merge = MergeWorker(self.root, self.engineering, self.store)


def _patched_run_once(self) -> dict:
    active = self.store.list_active()

    # A promoted candidate is not handed to Learning until the Merge submodule
    # independently records the exact promotion boundary.
    for record in sorted(
        (item for item in active if item.stage == "promoted"),
        key=lambda item: (item.updated_at, item.task_id),
    ):
        if _last_worker(record) != "merge":
            return {"handled": True, **self.merge.run(record)}
        return {"handled": True, **self.learning.run(record)}

    validation_waits: list[dict] = []
    for record in sorted(
        (item for item in active if item.stage == "validation_ready"),
        key=lambda item: (item.updated_at, item.task_id),
    ):
        outcome = self.validation.run(record)
        if outcome.get("action") != "pipeline_wait_validation":
            return {"handled": True, **outcome}
        validation_waits.append(outcome)

    stage_order = (
        "review_ready",
        "needs_development_revision",
        "needs_repair",
        "development_ready",
        "repair_ready",
        "discovered",
    )
    for stage in stage_order:
        candidates = sorted(
            (item for item in active if item.stage == stage),
            key=lambda item: (item.updated_at, item.task_id),
        )
        if not candidates:
            continue
        record = candidates[0]
        if stage == "review_ready":
            return {"handled": True, **self.review.run(record)}
        if stage in {"needs_development_revision", "development_ready"}:
            task = self.engineering.queue.get(record.task_id)
            if ImprovementModule.is_improvement_task(task, record):
                return {"handled": True, **self.improvement.run(record)}
            return {"handled": True, **self.development.run(record)}
        if stage in {"needs_repair", "repair_ready"}:
            return {"handled": True, **self.repair.run(record)}
        return {"handled": True, **self.triage.run(record)}

    discovery = self.discovery.run()
    if discovery.get("task_id") and discovery.get("target"):
        record = self.store.get(str(discovery["task_id"]))
        return {
            "handled": True,
            "action": "pipeline_issue_discovered",
            "discovery": discovery,
            "record": asdict(record) if record else {},
        }

    if discovery.get("status") in {"no_issue_found", "issue_known_terminal"} and not discovery.get(
        "cycle_complete", True
    ):
        return {
            "handled": True,
            "action": "pipeline_discovery_continue",
            "discovery": discovery,
        }

    if validation_waits:
        return {
            "handled": True,
            "action": "pipeline_wait_validation",
            "record": validation_waits[0].get("record", {}),
            "validation_waits": validation_waits,
            "discovery": discovery,
        }

    return {"handled": False, "action": "pipeline_no_issue_found", "discovery": discovery}


def install_improvement_merge_submodules() -> None:
    """Install the specialist split once for every Genesis entrypoint."""
    cls = BoundedAutonomyPipelineCoordinator
    if getattr(cls, "_genesis_improvement_merge_installed", False):
        return
    cls._genesis_improvement_merge_original_init = cls.__init__
    cls.__init__ = _patched_init
    cls.run_once = _patched_run_once
    cls._genesis_improvement_merge_installed = True

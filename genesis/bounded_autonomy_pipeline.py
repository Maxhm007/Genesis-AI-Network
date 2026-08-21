from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from .autonomy_pipeline import (
    AutonomyPipelineCoordinator,
    DiscoveryWorker,
    PipelineRecord,
    RepairWorker,
)
from .issue_discovery import GenesisIssueDiscoveryEngine, IssueDiscoveryCandidate


class _SelectedIssueDiscoveryEngine(GenesisIssueDiscoveryEngine):
    """Reuse the canonical discovery/enqueue logic for one preselected batch."""

    def __init__(self, root: Path, selected: list[IssueDiscoveryCandidate]) -> None:
        super().__init__(root)
        self._selected = list(selected)

    def rank_candidates(self, *, include_protected: bool = False) -> list[IssueDiscoveryCandidate]:
        if include_protected:
            return list(self._selected)
        return [candidate for candidate in self._selected if not candidate.protected]


class ResumableDiscoveryWorker(DiscoveryWorker):
    """Inspect a small rotating discovery batch per Pulse instead of monopolizing it."""

    BATCH_SIZE = 3

    def __init__(self, root: Path, engineering, store) -> None:
        super().__init__(root, engineering, store)
        self.cursor_path = self.engine.runtime / "pulse_cursor.json"

    def _fingerprint(self, ranked: list[IssueDiscoveryCandidate]) -> str:
        digest = hashlib.sha256()
        for candidate in ranked:
            path = self.root / candidate.path
            digest.update(candidate.path.encode("utf-8"))
            try:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            except OSError:
                digest.update(b"missing")
        return digest.hexdigest()

    def _load_cursor(self, fingerprint: str, total: int) -> tuple[int, int]:
        if not self.cursor_path.is_file():
            return 0, 0
        try:
            payload = json.loads(self.cursor_path.read_text(encoding="utf-8"))
        except Exception:
            return 0, 0
        if payload.get("fingerprint") != fingerprint:
            return 0, 0
        try:
            offset = int(payload.get("offset", 0))
            cycle = int(payload.get("cycle", 0))
        except (TypeError, ValueError):
            return 0, 0
        if offset < 0 or offset >= max(total, 1):
            offset = 0
        return offset, max(0, cycle)

    def _save_cursor(self, fingerprint: str, offset: int, cycle: int) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_path.write_text(
            json.dumps(
                {"fingerprint": fingerprint, "offset": offset, "cycle": cycle},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def run(self) -> dict:
        ranked = self.engine.rank_candidates(include_protected=False)
        if not ranked:
            result = _SelectedIssueDiscoveryEngine(self.root, []).discover_and_enqueue(
                self.engineering.queue, self.engineering.coding._provider()
            )
            result.update({"batch_offset": 0, "batch_size": 0, "cycle_complete": True, "discovery_cycle": 0})
            return result

        fingerprint = self._fingerprint(ranked)
        offset, cycle = self._load_cursor(fingerprint, len(ranked))
        selected = ranked[offset : offset + self.BATCH_SIZE]
        if not selected:
            offset = 0
            selected = ranked[: self.BATCH_SIZE]

        provider = self.engineering.coding._provider()
        batch_engine = _SelectedIssueDiscoveryEngine(self.root, selected)
        result = batch_engine.discover_and_enqueue(self.engineering.queue, provider)
        result["batch_offset"] = offset
        result["batch_size"] = len(selected)
        result["total_ranked"] = len(ranked)

        scanned_count = len(list(result.get("scanned") or []))
        if result.get("status") == "blocked":
            next_offset = offset
            cycle_complete = False
        else:
            consumed = scanned_count if scanned_count > 0 else len(selected)
            next_offset = min(len(ranked), offset + max(1, consumed))
            cycle_complete = next_offset >= len(ranked)
            if cycle_complete:
                next_offset = 0
                cycle += 1
        self._save_cursor(fingerprint, next_offset, cycle)
        result["next_batch_offset"] = next_offset
        result["cycle_complete"] = cycle_complete
        result["discovery_cycle"] = cycle

        task_id = str(result.get("task_id") or "")
        target = str(result.get("target") or "")
        if task_id and target:
            existing = self.store.get(task_id)
            queue_task = self.engineering.queue.get(task_id)
            terminal_pipeline = bool(existing and existing.stage in {"closed", "quarantined"})
            terminal_task = bool(queue_task and queue_task.state in {"complete", "quarantined", "cancelled"})
            if terminal_pipeline or terminal_task:
                result["status"] = "issue_known_terminal"
                result["known_task_id"] = task_id
                result["known_target"] = target
                result["task_id"] = None
                result["target"] = None
            else:
                self.store.register_discovery(task_id, target, result)
        return result


class SingleAttemptRepairWorker(RepairWorker):
    """Make one candidate attempt per Pulse; persist feedback for the next Pulse."""

    MAX_FEEDBACK_BYTES = 4_000

    @staticmethod
    def _normalize_path(path: object) -> str:
        return str(path).replace("\\", "/").lstrip("./")

    def run(self, record: PipelineRecord) -> dict:
        task = self.engineering.queue.get(record.task_id)
        if task is None:
            updated = self.store.transition(record.task_id, "quarantined", worker="repair", feedback="task_missing")
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        if record.repair_attempts >= task.max_attempts:
            updated = self.store.transition(
                record.task_id, "quarantined", worker="repair", feedback="repair_budget_exhausted"
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}

        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self.store.transition(record.task_id, "repair_ready", worker="repair", bump_repair=True)

        objective = task.objective
        if record.last_feedback:
            objective += (
                "\n\nPREVIOUS_PIPELINE_FEEDBACK: The previous bounded attempt did not pass. "
                "Use this evidence to revise the SAME issue; verify against current repository context and do not broaden scope.\n"
                + record.last_feedback[-self.MAX_FEEDBACK_BYTES :]
            )
        attempt_task = replace(task, objective=objective)

        old_revision_budget = self.engineering.MAX_CANDIDATE_REVISIONS
        self.engineering.MAX_CANDIDATE_REVISIONS = 0
        try:
            attempt = self.engineering._attempt_task(attempt_task, runtime)
        finally:
            self.engineering.MAX_CANDIDATE_REVISIONS = old_revision_budget

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
            changed_files = tuple(self._normalize_path(path) for path in (candidate.get("changed_files") or ()))
            if len(changed_files) != 1 or changed_files[0] != expected_target:
                scope_error = (
                    "repair_scope_violation: autonomous issue repair must change exactly the discovered target "
                    f"{expected_target}; candidate changed {list(changed_files)}"
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
                worker="repair",
                candidate_branch=branch,
                candidate_sha=candidate_sha,
                review_ref=review_ref,
            )
            return {
                "action": "pipeline_repair_completed",
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
            or "repair_failed"
        )[-self.MAX_FEEDBACK_BYTES :]
        current = self.engineering.queue.get(record.task_id)
        if current and current.state == "review":
            try:
                current = self.engineering.queue.transition(
                    current.task_id, "running", module_id="genesis.coding"
                )
            except Exception:
                current = self.engineering.queue.get(record.task_id)
        if current and current.state not in {"failed", "quarantined", "complete"}:
            try:
                current = self.engineering.queue.record_failure(
                    current.task_id,
                    feedback,
                    classification="pipeline_repair",
                    retry_after_seconds=0,
                    module_id="genesis.coding",
                )
            except Exception:
                current = self.engineering.queue.get(record.task_id)
        terminal = bool(current and current.state == "quarantined")
        updated = self.store.transition(
            record.task_id,
            "quarantined" if terminal else "needs_repair",
            worker="repair",
            feedback=feedback,
        )
        return {
            "action": "pipeline_quarantined" if terminal else "pipeline_repair_retry",
            "attempt": attempt,
            "record": asdict(updated),
        }


class BoundedAutonomyPipelineCoordinator(AutonomyPipelineCoordinator):
    """Non-blocking specialist scheduler for one short, resumable Pulse transition."""

    def __init__(self, root: Path, engineering=None) -> None:
        super().__init__(root, engineering)
        self.discovery = ResumableDiscoveryWorker(self.root, self.engineering, self.store)
        self.repair = SingleAttemptRepairWorker(self.root, self.engineering, self.store)

    def run_once(self) -> dict:
        active = self.store.list_active()

        # Finish promoted work first so lessons and task closure are durable.
        for record in sorted(
            (item for item in active if item.stage == "promoted"),
            key=lambda item: (item.updated_at, item.task_id),
        ):
            return {"handled": True, **self.learning.run(record)}

        # Poll independent validation without letting a waiting candidate starve
        # triage/repair/review work. Promotion observation is cheap and has no
        # authority to approve or merge a candidate.
        validation_waits: list[dict] = []
        for record in sorted(
            (item for item in active if item.stage == "validation_ready"),
            key=lambda item: (item.updated_at, item.task_id),
        ):
            outcome = self.validation.run(record)
            if outcome.get("action") != "pipeline_wait_validation":
                return {"handled": True, **outcome}
            validation_waits.append(outcome)

        # Executable internal work always outranks an unchanged validation wait.
        stage_order = ("review_ready", "needs_repair", "repair_ready", "discovered")
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

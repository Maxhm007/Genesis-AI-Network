from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .autonomous_engineering import AutonomousEngineeringLoop
from .coding import CodingModule
from .issue_discovery import AUTONOMOUS_REPAIR_EXCLUDED, GenesisIssueDiscoveryEngine
from .modules.task_queue import GenesisTask


ACTIVE_STAGES = (
    "discovered",
    "development_ready",
    "needs_development_revision",
    "repair_ready",
    "needs_repair",
    "review_ready",
    "validation_ready",
    "promoted",
)
TERMINAL_STAGES = {"closed", "quarantined"}
DEVELOPMENT_SOURCE = "genesis.evolution_learning"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_development_discovery(discovery: dict) -> bool:
    return str(discovery.get("source") or "") == DEVELOPMENT_SOURCE


@dataclass(frozen=True)
class PipelineRecord:
    task_id: str
    stage: str
    target_path: str
    candidate_branch: str | None
    candidate_sha: str | None
    review_ref: str | None
    development_attempts: int
    repair_attempts: int
    review_attempts: int
    last_feedback: str | None
    discovery: dict
    history: tuple[dict, ...]
    updated_at: str


class PipelineStore:
    """Pipeline metadata stored beside Genesis tasks in the same SQLite database.

    `genesis_tasks` remains the authoritative work queue. This table only records
    which specialist currently owns the same task and the evidence needed for the
    next handoff. There is no second competing task database or duplicate task ID.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS genesis_autonomy_pipeline (
                    task_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    candidate_branch TEXT,
                    candidate_sha TEXT,
                    review_ref TEXT,
                    development_attempts INTEGER NOT NULL DEFAULT 0,
                    repair_attempts INTEGER NOT NULL DEFAULT 0,
                    review_attempts INTEGER NOT NULL DEFAULT 0,
                    last_feedback TEXT,
                    discovery_json TEXT NOT NULL DEFAULT '{}',
                    history_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(genesis_autonomy_pipeline)").fetchall()
            }
            if "development_attempts" not in columns:
                db.execute(
                    "ALTER TABLE genesis_autonomy_pipeline "
                    "ADD COLUMN development_attempts INTEGER NOT NULL DEFAULT 0"
                )

            # Migrate already-queued learning upgrades out of legacy repair stages.
            rows = db.execute(
                "SELECT task_id, stage, repair_attempts, development_attempts, discovery_json "
                "FROM genesis_autonomy_pipeline WHERE stage IN ('repair_ready','needs_repair')"
            ).fetchall()
            for row in rows:
                try:
                    discovery = json.loads(row["discovery_json"] or "{}")
                except Exception:
                    continue
                if not is_development_discovery(discovery):
                    continue
                stage = (
                    "development_ready"
                    if row["stage"] == "repair_ready"
                    else "needs_development_revision"
                )
                development_attempts = max(
                    int(row["development_attempts"] or 0), int(row["repair_attempts"] or 0)
                )
                db.execute(
                    "UPDATE genesis_autonomy_pipeline "
                    "SET stage=?, development_attempts=?, repair_attempts=0 WHERE task_id=?",
                    (stage, development_attempts, row["task_id"]),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PipelineRecord:
        return PipelineRecord(
            task_id=row["task_id"],
            stage=row["stage"],
            target_path=row["target_path"],
            candidate_branch=row["candidate_branch"],
            candidate_sha=row["candidate_sha"],
            review_ref=row["review_ref"],
            development_attempts=int(row["development_attempts"]),
            repair_attempts=int(row["repair_attempts"]),
            review_attempts=int(row["review_attempts"]),
            last_feedback=row["last_feedback"],
            discovery=json.loads(row["discovery_json"] or "{}"),
            history=tuple(json.loads(row["history_json"] or "[]")),
            updated_at=row["updated_at"],
        )

    def get(self, task_id: str) -> PipelineRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM genesis_autonomy_pipeline WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_active(self) -> list[PipelineRecord]:
        placeholders = ",".join("?" for _ in ACTIVE_STAGES)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM genesis_autonomy_pipeline WHERE stage IN ({placeholders}) ORDER BY updated_at ASC",
                ACTIVE_STAGES,
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def register_discovery(self, task_id: str, target_path: str, discovery: dict) -> PipelineRecord:
        existing = self.get(task_id)
        if existing is not None:
            return existing
        now = utc_now()
        history = [{"at": now, "stage": "discovered", "worker": "discovery"}]
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO genesis_autonomy_pipeline (
                    task_id, stage, target_path, discovery_json, history_json, updated_at
                ) VALUES (?, 'discovered', ?, ?, ?, ?)
                """,
                (task_id, target_path, json.dumps(discovery, sort_keys=True), json.dumps(history), now),
            )
        record = self.get(task_id)
        assert record is not None
        return record

    def transition(
        self,
        task_id: str,
        stage: str,
        *,
        worker: str,
        feedback: str | None = None,
        candidate_branch: str | None = None,
        candidate_sha: str | None = None,
        review_ref: str | None = None,
        bump_development: bool = False,
        bump_repair: bool = False,
        bump_review: bool = False,
    ) -> PipelineRecord:
        current = self.get(task_id)
        if current is None:
            raise KeyError(task_id)
        now = utc_now()
        history = list(current.history)
        event: dict[str, Any] = {"at": now, "stage": stage, "worker": worker}
        if feedback:
            event["feedback"] = feedback[:2000]
        if candidate_sha:
            event["candidate_sha"] = candidate_sha
        history.append(event)
        branch = candidate_branch if candidate_branch is not None else current.candidate_branch
        sha = candidate_sha if candidate_sha is not None else current.candidate_sha
        review = review_ref if review_ref is not None else current.review_ref
        development_attempts = current.development_attempts + (1 if bump_development else 0)
        repair_attempts = current.repair_attempts + (1 if bump_repair else 0)
        review_attempts = current.review_attempts + (1 if bump_review else 0)
        last_feedback = feedback if feedback is not None else current.last_feedback
        with self._connect() as db:
            db.execute(
                """
                UPDATE genesis_autonomy_pipeline
                SET stage = ?, candidate_branch = ?, candidate_sha = ?, review_ref = ?,
                    development_attempts = ?, repair_attempts = ?, review_attempts = ?, last_feedback = ?,
                    history_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    stage,
                    branch,
                    sha,
                    review,
                    development_attempts,
                    repair_attempts,
                    review_attempts,
                    last_feedback,
                    json.dumps(history, sort_keys=True),
                    now,
                    task_id,
                ),
            )
        record = self.get(task_id)
        assert record is not None
        return record


class DiscoveryWorker:
    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store
        self.engine = GenesisIssueDiscoveryEngine(root)

    def run(self) -> dict:
        provider = self.engineering.coding._provider()
        result = self.engine.discover_and_enqueue(self.engineering.queue, provider)
        task_id = str(result.get("task_id") or "")
        target = str(result.get("target") or "")
        if task_id and target:
            self.store.register_discovery(task_id, target, result)
        return result


class TriageWorker:
    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store

    def run(self, record: PipelineRecord) -> dict:
        task = self.engineering.queue.get(record.task_id)
        if task is None:
            updated = self.store.transition(
                record.task_id, "quarantined", worker="triage", feedback="task_missing_from_shared_queue"
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        target = record.target_path.replace("\\", "/").lstrip("./")
        finding = dict(record.discovery.get("finding") or {})
        confidence = float(finding.get("confidence_normalized") or 0.0)
        reason = None
        if target in AUTONOMOUS_REPAIR_EXCLUDED:
            reason = "protected_target"
        elif not (self.root / target).is_file():
            reason = "target_missing"
        elif confidence < 0.55:
            reason = "discovery_confidence_below_threshold"
        if reason:
            updated = self.store.transition(record.task_id, "quarantined", worker="triage", feedback=reason)
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        if task.state == "new":
            task = self.engineering.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
        elif task.state not in {"assigned", "failed", "blocked"}:
            updated = self.store.transition(
                record.task_id,
                "quarantined",
                worker="triage",
                feedback=f"unexpected_task_state:{task.state}",
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}

        development = str(task.payload.get("source") or "") == DEVELOPMENT_SOURCE
        stage = "development_ready" if development else "repair_ready"
        updated = self.store.transition(record.task_id, stage, worker="triage")
        return {
            "action": "pipeline_development_triaged" if development else "pipeline_triaged",
            "task": asdict(task),
            "record": asdict(updated),
        }


class RepairWorker:
    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store

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
        attempt = self.engineering._attempt_task(task, runtime)
        candidate = dict(attempt.get("candidate") or {})
        security = dict(attempt.get("candidate_security") or {})
        if (
            attempt.get("coding_status") == "candidate_created"
            and candidate.get("committed")
            and candidate.get("commit_sha")
            and candidate.get("branch")
            and security.get("status") == "pass"
        ):
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

        current = self.engineering.queue.get(record.task_id)
        feedback = str(attempt.get("error") or attempt.get("coding_status") or "repair_failed")[:2000]
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


class DevelopmentWorker:
    """Implement new capabilities; use repair only after an implementation exists."""

    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store

    def run(self, record: PipelineRecord) -> dict:
        task = self.engineering.queue.get(record.task_id)
        if task is None:
            updated = self.store.transition(
                record.task_id, "quarantined", worker="development", feedback="task_missing"
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        if record.development_attempts >= task.max_attempts:
            updated = self.store.transition(
                record.task_id,
                "quarantined",
                worker="development",
                feedback="development_budget_exhausted",
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        self.store.transition(
            record.task_id, "development_ready", worker="development", bump_development=True
        )
        attempt = self.engineering._attempt_task(task, runtime)
        candidate = dict(attempt.get("candidate") or {})
        security = dict(attempt.get("candidate_security") or {})
        if (
            attempt.get("coding_status") == "candidate_created"
            and candidate.get("committed")
            and candidate.get("commit_sha")
            and candidate.get("branch")
            and security.get("status") == "pass"
        ):
            candidate_sha = str(candidate["commit_sha"])
            branch = str(candidate["branch"])
            review_ref = f"genesis/review-{candidate_sha[:12]}"
            updated = self.store.transition(
                record.task_id,
                "review_ready",
                worker="development",
                candidate_branch=branch,
                candidate_sha=candidate_sha,
                review_ref=review_ref,
            )
            return {
                "action": "pipeline_development_completed",
                "attempt": attempt,
                "record": asdict(updated),
                "review_candidate": {
                    "branch": branch,
                    "candidate_sha": candidate_sha,
                    "review_ref": review_ref,
                },
            }

        current = self.engineering.queue.get(record.task_id)
        feedback = str(
            attempt.get("error") or attempt.get("coding_status") or "development_attempt_failed"
        )[:2000]
        if current and current.state not in {"failed", "quarantined", "complete"}:
            try:
                current = self.engineering.queue.record_failure(
                    current.task_id,
                    feedback,
                    classification="pipeline_development",
                    retry_after_seconds=0,
                    module_id="genesis.coding",
                )
            except Exception:
                current = self.engineering.queue.get(record.task_id)
        terminal = bool(current and current.state == "quarantined")
        updated = self.store.transition(
            record.task_id,
            "quarantined" if terminal else "needs_development_revision",
            worker="development",
            feedback=feedback,
        )
        return {
            "action": "pipeline_quarantined" if terminal else "pipeline_development_retry",
            "attempt": attempt,
            "record": asdict(updated),
        }


class ReviewWorker:
    MAX_DIFF_BYTES = 14_000
    MAX_FEEDBACK_BYTES = 4_000

    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=False)

    @staticmethod
    def _is_development(record: PipelineRecord, task) -> bool:
        if task is not None and str(task.payload.get("source") or "") == DEVELOPMENT_SOURCE:
            return True
        return is_development_discovery(record.discovery)

    def _send_back(self, record: PipelineRecord, feedback: str) -> dict:
        task = self.engineering.queue.get(record.task_id)
        development = self._is_development(record, task)
        if task and task.state == "review":
            task = self.engineering.queue.transition(task.task_id, "running", module_id="genesis.coding")
        if task and task.state not in {"failed", "quarantined", "complete"}:
            try:
                task = self.engineering.queue.record_failure(
                    task.task_id,
                    feedback[: self.MAX_FEEDBACK_BYTES],
                    classification="internal_development_review" if development else "internal_review",
                    retry_after_seconds=0,
                    module_id="genesis.coding",
                )
            except Exception:
                task = self.engineering.queue.get(record.task_id)
        terminal = bool(task and task.state == "quarantined")
        retry_stage = "needs_development_revision" if development else "needs_repair"
        updated = self.store.transition(
            record.task_id,
            "quarantined" if terminal else retry_stage,
            worker="review",
            feedback=feedback,
            bump_review=True,
        )
        retry_action = (
            "pipeline_internal_review_needs_development"
            if development
            else "pipeline_internal_review_needs_repair"
        )
        return {
            "action": "pipeline_quarantined" if terminal else retry_action,
            "record": asdict(updated),
            "feedback": feedback[: self.MAX_FEEDBACK_BYTES],
        }

    def run(self, record: PipelineRecord) -> dict:
        if not record.candidate_sha or not record.candidate_branch or not record.review_ref:
            return self._send_back(record, "review_candidate_metadata_missing")
        self._git("fetch", "origin", f"{record.review_ref}:refs/remotes/origin/{record.review_ref}")
        exists = self._git("cat-file", "-e", f"{record.candidate_sha}^{{commit}}")
        if exists.returncode != 0:
            return self._send_back(record, "review_candidate_not_available")
        checkout = self._git("checkout", "--detach", record.candidate_sha)
        if checkout.returncode != 0:
            return self._send_back(record, "review_candidate_checkout_failed:" + checkout.stderr[-1200:])

        tests = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            timeout=900,
        )
        test_output = (tests.stdout + "\n" + tests.stderr)[-self.MAX_FEEDBACK_BYTES :]
        if tests.returncode != 0:
            return self._send_back(record, "internal_full_test_failure:\n" + test_output)

        task = self.engineering.queue.get(record.task_id)
        if task is None:
            return self._send_back(record, "review_task_missing")
        self._git("fetch", "origin", "main")
        diff = self._git("diff", "origin/main...HEAD", "--", record.target_path).stdout
        diff = diff.encode("utf-8", errors="replace")[: self.MAX_DIFF_BYTES].decode("utf-8", errors="replace")
        provider = self.engineering.coding._provider()
        if provider is None or str(getattr(provider, "name", "")) == "genesis-bootstrap":
            return self._send_back(record, "internal_review_requires_non_bootstrap_provider")
        prompt = (
            "ROLE: genesis_internal_code_reviewer\n"
            "Review this already test-passing Genesis candidate independently from the implementation or repair attempt. "
            "Return JSON only with decision and feedback. decision must be approve or needs_repair. "
            "Approve only if the candidate addresses the objective without unrelated behavior changes, hidden regressions, "
            "or weakened safety/validation boundaries. Do not ask for style-only refactoring.\n"
            f"OBJECTIVE: {task.objective}\n"
            f"TARGET: {record.target_path}\n"
            f"CANDIDATE_SHA: {record.candidate_sha}\n"
            f"TEST_RESULT: pass\n"
            f"DIFF:\n{diff}\n"
        )
        try:
            payload = CodingModule._extract_json(provider.reason(prompt))
        except Exception as exc:
            return self._send_back(record, f"internal_review_provider_error:{type(exc).__name__}:{exc}")
        decision = str(payload.get("decision") or "").strip().lower()
        feedback = str(payload.get("feedback") or "").strip()[: self.MAX_FEEDBACK_BYTES]
        if decision != "approve":
            return self._send_back(record, feedback or "internal_reviewer_requested_revision")
        updated = self.store.transition(
            record.task_id,
            "validation_ready",
            worker="review",
            feedback=feedback or "internal_review_approved",
            bump_review=True,
        )
        return {
            "action": "pipeline_internal_review_approved",
            "record": asdict(updated),
            "validation_candidate": {
                "branch": record.candidate_branch,
                "candidate_sha": record.candidate_sha,
            },
        }


class ValidationWorker:
    """Observe the existing independent validators/promotion path; never bypass it."""

    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=False)

    def _promoted(self, candidate_sha: str) -> bool:
        self._git("fetch", "origin", "main")
        direct = self._git("merge-base", "--is-ancestor", candidate_sha, "origin/main")
        if direct.returncode == 0:
            return True
        # Candidate Promotion may safely rebase a queued candidate onto a newer
        # main. `git cherry` recognizes an equivalent patch even when SHA changes.
        cherry = self._git("cherry", "origin/main", candidate_sha)
        lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
        return bool(lines) and all(line.startswith("-") for line in lines)

    def run(self, record: PipelineRecord) -> dict:
        if not record.candidate_sha:
            updated = self.store.transition(
                record.task_id, "quarantined", worker="validation", feedback="candidate_sha_missing"
            )
            return {"action": "pipeline_quarantined", "record": asdict(updated)}
        if not self._promoted(record.candidate_sha):
            return {"action": "pipeline_wait_validation", "record": asdict(record)}
        updated = self.store.transition(record.task_id, "promoted", worker="promotion")
        return {"action": "pipeline_promotion_observed", "record": asdict(updated)}


class LearningWorker:
    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop, store: PipelineStore) -> None:
        self.root = root
        self.engineering = engineering
        self.store = store
        self.path = root / "runtime" / "autonomy_pipeline" / "lessons.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def run(self, record: PipelineRecord) -> dict:
        task = self.engineering.queue.get(record.task_id)
        lesson = {
            "at": utc_now(),
            "task_id": record.task_id,
            "target": record.target_path,
            "objective": task.objective if task else None,
            "candidate_sha": record.candidate_sha,
            "development_attempts": record.development_attempts,
            "repair_attempts": record.repair_attempts,
            "review_attempts": record.review_attempts,
            "last_feedback": record.last_feedback,
            "pipeline_history": list(record.history),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lesson, sort_keys=True) + "\n")
        if task and task.state == "review":
            self.engineering.queue.transition(task.task_id, "complete", module_id="genesis.self_learning")
        learned = self.store.transition(record.task_id, "closed", worker="learning")
        return {"action": "pipeline_learning_completed", "record": asdict(learned), "lesson": lesson}


class AutonomyPipelineCoordinator:
    """Route one bounded queue transition to one specialist per Gene Pulse."""

    def __init__(self, root: Path, engineering: AutonomousEngineeringLoop | None = None) -> None:
        self.root = Path(root).resolve()
        self.engineering = engineering or AutonomousEngineeringLoop(self.root)
        self.store = PipelineStore(self.engineering.queue.path)
        self.discovery = DiscoveryWorker(self.root, self.engineering, self.store)
        self.triage = TriageWorker(self.root, self.engineering, self.store)
        self.development = DevelopmentWorker(self.root, self.engineering, self.store)
        self.repair = RepairWorker(self.root, self.engineering, self.store)
        self.review = ReviewWorker(self.root, self.engineering, self.store)
        self.validation = ValidationWorker(self.root, self.engineering, self.store)
        self.learning = LearningWorker(self.root, self.engineering, self.store)

    @staticmethod
    def _priority(stage: str) -> int:
        return {
            "promoted": 0,
            "validation_ready": 1,
            "review_ready": 2,
            "needs_development_revision": 3,
            "needs_repair": 3,
            "development_ready": 4,
            "repair_ready": 4,
            "discovered": 5,
        }.get(stage, 99)

    def is_pipeline_task(self, task: GenesisTask | None) -> bool:
        if task is None:
            return False
        source = str(task.payload.get("source") or "")
        return self.store.get(task.task_id) is not None or source in {
            "genesis.issue_discovery",
            DEVELOPMENT_SOURCE,
        }

    def run_once(self) -> dict:
        active = self.store.list_active()
        if active:
            active.sort(key=lambda record: (self._priority(record.stage), record.updated_at, record.task_id))
            record = active[0]
            if record.stage == "discovered":
                return {"handled": True, **self.triage.run(record)}
            if record.stage in {"development_ready", "needs_development_revision"}:
                return {"handled": True, **self.development.run(record)}
            if record.stage in {"repair_ready", "needs_repair"}:
                return {"handled": True, **self.repair.run(record)}
            if record.stage == "review_ready":
                return {"handled": True, **self.review.run(record)}
            if record.stage == "validation_ready":
                return {"handled": True, **self.validation.run(record)}
            if record.stage == "promoted":
                return {"handled": True, **self.learning.run(record)}

        discovery = self.discovery.run()
        if discovery.get("task_id") and discovery.get("target"):
            return {
                "handled": True,
                "action": "pipeline_issue_discovered",
                "discovery": discovery,
                "record": asdict(self.store.get(str(discovery["task_id"]))),
            }
        return {"handled": False, "action": "pipeline_no_issue_found", "discovery": discovery}

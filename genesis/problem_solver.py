from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from .job_failure import JobFailureIntelligence
from .modules.task_queue import GenesisTask


AUTHORITY_HINTS = (
    "permission denied",
    "forbidden",
    "requires admin",
    "requires owner",
    "requires authentication",
    "not authorized",
    "insufficient permission",
    "secret management permission",
    "external authority",
)
SECURITY_HINTS = (
    "secret guard",
    "credential-like content",
    "security review",
    "policy violation",
    "unsafe",
)
TEST_HINTS = (
    "assertionerror",
    "failed tests",
    "test failed",
    "pytest",
    "regression",
)
ENVIRONMENT_HINTS = (
    "runner image",
    "environment",
    "dependency",
    "command not found",
    "module not found",
    "importerror",
)


@dataclass(frozen=True)
class ProblemDiagnosis:
    classification: str
    root_cause: str
    repair_strategy: str
    evidence: tuple[str, ...]
    retry_allowed: bool
    owner_action_required: bool
    next_module: str
    remember_as: str

    def as_dict(self) -> dict:
        return asdict(self)


class AutonomousProblemSolver:
    """Meta-controller for bounded diagnose -> repair -> validate loops.

    It never bypasses policy, security, promotion or owner authority. Failures
    become explicit diagnoses and durable lessons so later attempts change
    strategy rather than blindly repeating the same action.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.history_path = self.runtime / "problem_solver_history.jsonl"

    @staticmethod
    def _contains(text: str, hints: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(hint in lowered for hint in hints)

    def diagnose(self, task: GenesisTask, evidence: list[str] | tuple[str, ...] = ()) -> ProblemDiagnosis:
        combined = "\n".join([task.last_error or "", *[str(item) for item in evidence]])
        base = JobFailureIntelligence.classify(combined)

        if self._contains(combined, AUTHORITY_HINTS):
            return ProblemDiagnosis(
                "external_authority",
                "The repair requires an authenticated or owner-controlled capability Genesis does not currently possess.",
                "record_blocker_and_request_minimal_owner_action",
                tuple(str(item) for item in evidence),
                False,
                True,
                "genesis.automation",
                "authority_boundary",
            )
        if self._contains(combined, SECURITY_HINTS):
            return ProblemDiagnosis(
                "security_rejection",
                "A security/policy gate rejected the candidate; inspect the exact finding and rebuild a clean candidate without weakening the gate.",
                "repair_candidate_and_resubmit_clean_history",
                tuple(str(item) for item in evidence),
                True,
                False,
                "genesis.security",
                "security_gate_failure",
            )
        if self._contains(combined, TEST_HINTS) or base == "validation":
            return ProblemDiagnosis(
                "test_or_validation_regression",
                "The candidate violates an existing behavioral contract or test expectation.",
                "isolate_failing_contract_patch_candidate_and_rerun_full_validation",
                tuple(str(item) for item in evidence),
                True,
                False,
                "genesis.coding",
                "validation_regression",
            )
        if self._contains(combined, ENVIRONMENT_HINTS) or base == "dependency":
            return ProblemDiagnosis(
                "environment_or_dependency",
                "The execution environment or dependency set prevents the intended action from running.",
                "repair_environment_or_dependency_then_retry",
                tuple(str(item) for item in evidence),
                True,
                False,
                "genesis.coding",
                "environment_failure",
            )
        if base == "transient":
            return ProblemDiagnosis(
                "transient",
                "The failure appears temporary rather than architectural.",
                "bounded_backoff_then_retry_same_strategy",
                tuple(str(item) for item in evidence),
                task.attempt_count < task.max_attempts,
                False,
                task.module_id or "genesis.automation",
                "transient_failure",
            )
        if base == "capability_gap":
            return ProblemDiagnosis(
                "capability_gap",
                "Genesis lacks a required capability for the current objective.",
                "recruit_specialist_or_build_bounded_capability_candidate",
                tuple(str(item) for item in evidence),
                True,
                False,
                "genesis.coding",
                "capability_gap",
            )
        return ProblemDiagnosis(
            "unknown",
            "Available evidence is insufficient for a confident root cause.",
            "collect_more_logs_compare_last_attempt_and_change_one_hypothesis",
            tuple(str(item) for item in evidence),
            task.attempt_count < task.max_attempts,
            False,
            "genesis.coding",
            "unknown_failure_needs_evidence",
        )

    def record(self, task: GenesisTask, diagnosis: ProblemDiagnosis) -> dict:
        previous = [
            row for row in task.failure_history
            if str(row.get("classification", "")) == diagnosis.classification
        ]
        payload = {
            "task_id": task.task_id,
            "objective": task.objective,
            "attempt_count": task.attempt_count,
            "classification": diagnosis.classification,
            "root_cause": diagnosis.root_cause,
            "repair_strategy": diagnosis.repair_strategy,
            "next_module": diagnosis.next_module,
            "retry_allowed": diagnosis.retry_allowed,
            "owner_action_required": diagnosis.owner_action_required,
            "remember_as": diagnosis.remember_as,
            "same_class_failures": len(previous),
            "strategy_change_required": len(previous) > 0 and diagnosis.classification != "transient",
            "evidence": list(diagnosis.evidence),
        }
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return payload

    def solve_step(self, task: GenesisTask, evidence: list[str] | tuple[str, ...] = ()) -> dict:
        diagnosis = self.diagnose(task, evidence)
        memory = self.record(task, diagnosis)
        return {
            "status": "blocked_external_authority" if diagnosis.owner_action_required else "repair_candidate_required",
            "diagnosis": diagnosis.as_dict(),
            "memory": memory,
            "loop": ["observe", "diagnose", "repair", "test", "validate", "remember"],
        }

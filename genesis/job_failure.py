from __future__ import annotations

from dataclasses import asdict, dataclass

from .modules.task_queue import GenesisTask


TRANSIENT_HINTS = (
    "timeout",
    "temporarily unavailable",
    "rate limit",
    "connection reset",
    "connection refused",
    "network",
    "429",
    "502",
    "503",
    "504",
)
DEPENDENCY_HINTS = (
    "module not found",
    "importerror",
    "missing dependency",
    "package not found",
    "command not found",
    "no such file",
)
VALIDATION_HINTS = (
    "assertionerror",
    "test failed",
    "validation failed",
    "schema",
    "contract",
)
CAPABILITY_HINTS = (
    "unsupported",
    "not implemented",
    "capability gap",
    "no provider",
    "cannot perform",
)


@dataclass(frozen=True)
class RecoveryPlan:
    classification: str
    action: str
    module_id: str | None
    use_ai_team: bool
    recruit_specialist: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class JobFailureIntelligence:
    """Classify failed Genesis jobs and choose a bounded recovery strategy."""

    @staticmethod
    def classify(error: str | None) -> str:
        text = (error or "").lower()
        if any(hint in text for hint in TRANSIENT_HINTS):
            return "transient"
        if any(hint in text for hint in DEPENDENCY_HINTS):
            return "dependency"
        if any(hint in text for hint in VALIDATION_HINTS):
            return "validation"
        if any(hint in text for hint in CAPABILITY_HINTS):
            return "capability_gap"
        return "unknown"

    @classmethod
    def plan(cls, task: GenesisTask) -> RecoveryPlan:
        classification = cls.classify(task.last_error)
        attempts = task.attempt_count
        owner = task.module_id

        if classification == "transient" and attempts <= 2:
            return RecoveryPlan(
                classification,
                "retry_same_module",
                owner,
                False,
                False,
                "Transient infrastructure/provider failure; retry the existing owner after backoff.",
            )

        if classification == "dependency":
            return RecoveryPlan(
                classification,
                "repair_dependency_then_retry",
                "genesis.coding",
                True,
                attempts >= 2,
                "A dependency/runtime defect needs bounded software repair before the original job is retried.",
            )

        if classification == "validation":
            return RecoveryPlan(
                classification,
                "independent_review_then_retry",
                owner or "genesis.coding",
                True,
                False,
                "Validation failure requires independent review rather than blind repetition.",
            )

        if classification == "capability_gap":
            return RecoveryPlan(
                classification,
                "recruit_specialist_and_expand_capability",
                "genesis.coding",
                True,
                True,
                "Current capability is insufficient; recruit a bounded specialist and produce a validated capability candidate.",
            )

        if attempts >= 2:
            return RecoveryPlan(
                classification,
                "diagnose_with_ai_team",
                "genesis.coding",
                True,
                True,
                "Repeated unknown failures should switch from blind retry to root-cause diagnosis with a specialist team.",
            )

        return RecoveryPlan(
            classification,
            "retry_with_diagnostics",
            owner,
            False,
            False,
            "First unknown failure; preserve ownership, collect diagnostics, and retry after backoff.",
        )

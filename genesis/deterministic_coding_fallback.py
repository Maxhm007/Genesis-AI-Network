from __future__ import annotations

from types import MethodType

from .autonomous_engineering import AutonomousEngineeringLoop
from .deterministic_benchmark_builder import DeterministicBenchmarkIntegrationProvider


INSTALL_MARKER = "_genesis_deterministic_coding_fallback_installed"
_ORIGINAL_ATTEMPT_TASK = AutonomousEngineeringLoop._attempt_task
_BOUNDED_FAILURES = {
    "provider_or_candidate_error": "benchmark_coding_provider_or_candidate_error",
    "candidate_not_committed": "benchmark_candidate_tests_or_execution_failed",
    "candidate_rejected_by_security": "benchmark_candidate_security_rejected",
}


def _is_benchmark_runner_task(task) -> bool:
    payload = getattr(task, "payload", {}) or {}
    return isinstance(payload, dict) and str(payload.get("task_type") or "") == "benchmark_runner_integration"


def _record_bounded_benchmark_failure(self: AutonomousEngineeringLoop, task, result: dict) -> dict:
    """Persist benchmark coding failures so the planner can change strategy.

    Ordinary coding behavior is untouched. A benchmark integration that returns to
    ``blocked`` after a bounded provider/proposal/test/security failure consumes the
    persistent task retry budget. Once the budget is exhausted, the existing queue
    quarantines that task and BenchmarkExecutionPlanner can create the next strategy
    generation instead of selecting the same broken task forever.
    """
    if not _is_benchmark_runner_task(task):
        return result

    status = str(result.get("coding_status") or "")
    classification = _BOUNDED_FAILURES.get(status)
    if classification is None:
        return result

    current = self.queue.get(task.task_id)
    if current is None or current.state != "blocked":
        return result

    error = str(result.get("error") or status or "benchmark coding failure").strip()
    updated = self.queue.record_failure(
        task.task_id,
        error,
        classification=classification,
        module_id=current.module_id,
    )
    result["failure_accounting"] = {
        "classification": classification,
        "attempt_count": updated.attempt_count,
        "max_attempts": updated.max_attempts,
        "state": updated.state,
        "strategy_generation_can_advance": updated.state == "quarantined",
    }
    return result


def _attempt_task_with_deterministic_benchmark(
    self: AutonomousEngineeringLoop,
    task,
    runtime,
):
    provider = DeterministicBenchmarkIntegrationProvider.for_task(
        self.root,
        task,
        self.coding,
    )
    if provider is None:
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        return _record_bounded_benchmark_failure(self, task, result)

    had_override = "_coding_provider" in self.__dict__
    previous_override = self.__dict__.get("_coding_provider")

    def deterministic_provider(_self):
        return provider

    self._coding_provider = MethodType(deterministic_provider, self)
    try:
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
    finally:
        if had_override:
            self.__dict__["_coding_provider"] = previous_override
        else:
            self.__dict__.pop("_coding_provider", None)

    result["provider_policy"] = "deterministic_benchmark_template_then_non_qwen"
    if result.get("coding_strategy") == "external_non_qwen_provider":
        result["coding_strategy"] = "deterministic_benchmark_integration"
    return _record_bounded_benchmark_failure(self, task, result)


def install_deterministic_coding_fallback() -> None:
    """Install the deterministic benchmark lane once after provider policy hooks."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_deterministic_benchmark
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

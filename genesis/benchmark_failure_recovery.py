from __future__ import annotations

from .autonomous_engineering import AutonomousEngineeringLoop


INSTALL_MARKER = "_genesis_benchmark_failure_recovery_installed"
_ORIGINAL_ATTEMPT_TASK = AutonomousEngineeringLoop._attempt_task
_BOUNDED_FAILURES = {
    "provider_or_candidate_error": "benchmark_coding_provider_or_candidate_error",
    "candidate_not_committed": "benchmark_candidate_tests_or_execution_failed",
    "candidate_rejected_by_security": "benchmark_candidate_security_rejected",
}


def _is_benchmark_runner_task(task) -> bool:
    payload = getattr(task, "payload", {}) or {}
    return isinstance(payload, dict) and str(payload.get("task_type") or "") == "benchmark_runner_integration"


def _attempt_task_with_bounded_benchmark_failures(self: AutonomousEngineeringLoop, task, runtime):
    """Persist benchmark coding failures so bounded strategy generations can advance.

    AutonomousEngineeringLoop historically moved provider/proposal failures back to
    ``blocked`` without incrementing the persistent task attempt counter. A blocked
    benchmark-runner task is immediately eligible again, so malformed code could be
    regenerated forever and BenchmarkExecutionPlanner never got a terminal task from
    which to create the next strategy generation.

    Only benchmark-runner integration work is changed here. Waiting-for-provider is
    not a failure, successful candidates keep the normal review path, and all existing
    tests, Security, materiality, independent validation, quorum and promotion gates
    remain authoritative.
    """
    result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
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


def install_benchmark_failure_recovery() -> None:
    """Install bounded benchmark failure accounting after coding-provider hooks."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_bounded_benchmark_failures
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

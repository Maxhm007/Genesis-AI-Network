from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from genesis.modules.task_queue import GenesisTask
from genesis.problem_solver import AutonomousProblemSolver
from genesis.task_router import TaskRouterModule


def _task(error: str, *, attempts: int = 1, history: tuple[dict, ...] = ()) -> GenesisTask:
    now = datetime.now(timezone.utc).isoformat()
    return GenesisTask(
        task_id="task-problem",
        objective="repair failed Genesis candidate",
        module_id="genesis.coding",
        state="failed",
        priority=90,
        payload={},
        created_at=now,
        updated_at=now,
        attempt_count=attempts,
        max_attempts=5,
        next_retry_at=None,
        last_error=error,
        failure_history=history,
    )


def test_security_rejection_requires_clean_repair_not_gate_bypass(tmp_path: Path) -> None:
    solver = AutonomousProblemSolver(tmp_path)
    result = solver.solve_step(
        _task("Secret Guard rejected candidate"),
        evidence=["credential-like content detected in test fixture"],
    )
    diagnosis = result["diagnosis"]
    assert diagnosis["classification"] == "security_rejection"
    assert diagnosis["next_module"] == "genesis.security"
    assert diagnosis["owner_action_required"] is False
    assert "resubmit_clean_history" in diagnosis["repair_strategy"]
    assert solver.history_path.is_file()


def test_external_authority_is_not_blindly_retried(tmp_path: Path) -> None:
    solver = AutonomousProblemSolver(tmp_path)
    diagnosis = solver.diagnose(
        _task("Action requires owner permission"),
        evidence=["secret management permission is unavailable"],
    )
    assert diagnosis.classification == "external_authority"
    assert diagnosis.owner_action_required is True
    assert diagnosis.retry_allowed is False


def test_repeat_non_transient_failure_requires_strategy_change(tmp_path: Path) -> None:
    solver = AutonomousProblemSolver(tmp_path)
    task = _task(
        "test failed",
        attempts=2,
        history=(
            {
                "attempt": 1,
                "classification": "test_or_validation_regression",
                "error": "test failed",
            },
        ),
    )
    diagnosis = solver.diagnose(task, evidence=["AssertionError"])
    memory = solver.record(task, diagnosis)
    assert diagnosis.classification == "test_or_validation_regression"
    assert memory["strategy_change_required"] is True


def test_router_pauses_failed_task_at_external_authority_boundary(tmp_path: Path) -> None:
    router = TaskRouterModule(tmp_path)
    created = router.queue.create(
        "Provision persistent node identity",
        module_id="genesis.automation",
        priority=90,
        max_attempts=5,
    )
    failed = router.queue.record_failure(
        created.task_id,
        "requires owner permission for secret management",
        retry_after_seconds=0,
    )
    assert failed.state == "failed"

    result = router.assign_next()
    assert result["status"] == "blocked_external_authority"
    paused = router.queue.get(created.task_id)
    assert paused is not None
    assert paused.state == "paused"
    assert "External authority required" in (paused.state_reason or "")


def test_router_routes_validation_failure_to_coding_with_problem_context(tmp_path: Path) -> None:
    router = TaskRouterModule(tmp_path)
    created = router.queue.create(
        "Repair candidate regression",
        module_id="genesis.updater",
        priority=90,
        max_attempts=5,
    )
    router.queue.record_failure(created.task_id, "AssertionError: test failed", retry_after_seconds=0)
    result = router.assign_next()
    assert result["status"] == "assigned"
    assert result["decision"]["module_id"] == "genesis.coding"
    assert result["problem_solver"]["diagnosis"]["classification"] == "test_or_validation_regression"
    assert result["ai_team_module"] == "genesis.ai_team"

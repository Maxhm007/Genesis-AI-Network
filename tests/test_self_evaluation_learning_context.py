from __future__ import annotations

from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop


def test_self_evaluation_context_includes_completed_development(tmp_path: Path) -> None:
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    task = loop.queue.create(
        "Improve routing with validated history",
        module_id="genesis.coding",
        payload={"task_type": "self_development", "source": "test"},
    )
    loop.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    loop.queue.transition(task.task_id, "running", module_id="genesis.coding")
    loop.queue.transition(task.task_id, "review", module_id="genesis.coding")
    loop.queue.transition(task.task_id, "complete", module_id="genesis.coding")

    context = loop._self_evaluation_context()
    assert "completed_self_development_tasks" in context
    assert "Improve routing with validated history" in context
    assert len(context.encode("utf-8")) <= loop.MAX_SELF_EVALUATION_CONTEXT_BYTES


def test_attempt_uses_self_evaluation_as_advisory_memory(monkeypatch, tmp_path: Path) -> None:
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    completed = loop.queue.create(
        "Previously completed bounded improvement",
        module_id="genesis.coding",
        payload={"task_type": "self_development"},
    )
    loop.queue.transition(completed.task_id, "assigned", module_id="genesis.coding")
    loop.queue.transition(completed.task_id, "running", module_id="genesis.coding")
    loop.queue.transition(completed.task_id, "review", module_id="genesis.coding")
    loop.queue.transition(completed.task_id, "complete", module_id="genesis.coding")
    current = loop.queue.create("Implement next safe improvement", module_id="genesis.coding")

    captured = {}

    def fake_attempt(self, task, runtime):
        captured["objective"] = task.objective
        return {"coding_status": "idle"}

    monkeypatch.setattr(AutonomousEngineeringLoop, "_attempt_task", fake_attempt)
    result = loop._attempt_task(current, tmp_path / "runtime")

    assert "GENESIS_SELF_EVALUATION_MEMORY" in captured["objective"]
    assert "Previously completed bounded improvement" in captured["objective"]
    assert "cannot award capability credit" in captured["objective"]
    assert result["self_evaluation_context_used"] is True
    assert result["self_evaluation_context_bytes"] > 0

from __future__ import annotations

import subprocess
from pathlib import Path

import genesis.autonomy_pipeline as pipeline_module
from genesis.autonomy_pipeline import PipelineStore, ReviewWorker
from genesis.modules.task_queue import PersistentTaskQueue


class _ReviewerProvider:
    name = "reviewer-provider"

    def reason(self, prompt: str) -> str:
        assert "TEST_RESULT: pass" in prompt
        return '{"decision":"approve","feedback":"review approved"}'


class _ExecutorStub:
    def __init__(self, env: dict[str, str]) -> None:
        self.env = env

    def _candidate_test_env(self) -> dict[str, str]:
        return self.env


class _CodingStub:
    def __init__(self, env: dict[str, str]) -> None:
        self.executor = _ExecutorStub(env)
        self.provider = _ReviewerProvider()

    def _provider(self):
        return self.provider


class _EngineeringStub:
    def __init__(self, queue: PersistentTaskQueue, env: dict[str, str]) -> None:
        self.queue = queue
        self.coding = _CodingStub(env)


def test_internal_review_uses_candidate_test_environment_after_checkout(tmp_path: Path, monkeypatch) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Review one learned capability",
        module_id="genesis.coding",
        payload={"source": "genesis.evolution_learning"},
        max_attempts=4,
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.transition(task.task_id, "review", module_id="genesis.coding")

    store = PipelineStore(queue.path)
    record = store.register_discovery(
        task.task_id,
        "genesis/learned_capabilities.py",
        {
            "source": "genesis.evolution_learning",
            "finding": {"confidence_normalized": 0.9, "grounded": True, "new_capability": True},
        },
    )
    record = store.transition(
        record.task_id,
        "review_ready",
        worker="development",
        candidate_branch="genesis/candidate-learning",
        candidate_sha="deadbeef",
        review_ref="genesis/review-deadbeef",
    )

    expected_env = {"PYTHONPATH": str(tmp_path), "SAFE_SENTINEL": "1"}
    worker = ReviewWorker(tmp_path, _EngineeringStub(queue, expected_env), store)
    worker._git = lambda *args: subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(args, 0, stdout="1 passed", stderr="")

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    result = worker.run(record)

    assert result["action"] == "pipeline_internal_review_approved"
    assert captured["args"] == ["python", "-m", "pytest", "-q"]
    assert captured["env"] is expected_env
    assert store.get(task.task_id).stage == "validation_ready"

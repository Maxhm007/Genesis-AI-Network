from __future__ import annotations

from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.autonomy_pipeline import PipelineStore
from genesis.bounded_autonomy_pipeline import SingleAttemptRepairWorker
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import ProviderRegistry
from genesis.pulse import GenePulse


class TrackingQwenProvider:
    name = "qwen2.5-coder-1.5b-gene-pulse"

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.calls += 1
        return '{"edits":[{"path":"genesis/worker.py","start_line":1,"end_line":1,"new":"VALUE = 2"}]}'


class StrongCodingProvider:
    name = "strong-coding-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"edits":[{"path":"genesis/worker.py","start_line":1,"end_line":1,"new":"VALUE = 3"}]}'


def _write_target(root: Path) -> None:
    path = root / "genesis" / "worker.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")


def _task(root: Path):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Improve the bounded worker implementation.",
        module_id="genesis.coding",
        payload={
            "source": "genesis.issue_discovery",
            "target_path": "genesis/worker.py",
            "context_paths": ["genesis/worker.py"],
        },
        max_attempts=4,
    )
    return queue, task


def test_qwen_is_selected_when_it_is_the_only_eligible_coder(tmp_path: Path) -> None:
    _write_target(tmp_path)
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)

    selected = loop._coding_provider()

    assert selected is qwen


def test_qwen_can_generate_a_bounded_repository_edit(tmp_path: Path) -> None:
    _write_target(tmp_path)
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)

    selected = loop._coding_provider()
    proposal = loop.coding.propose(
        "Change the bounded worker value from 1 to 2.",
        context_paths=["genesis/worker.py"],
        provider=selected,
    )

    assert qwen.calls == 1
    assert proposal.provider == qwen.name
    assert proposal.files["genesis/worker.py"] == "VALUE = 2\n"


def test_stronger_non_qwen_coder_wins_an_equal_reliability_tie(tmp_path: Path) -> None:
    _write_target(tmp_path)
    qwen = TrackingQwenProvider()
    strong = StrongCodingProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    registry.register(strong)
    loop = AutonomousEngineeringLoop(tmp_path, registry)

    selected = loop._coding_provider()

    assert selected is strong
    assert qwen.calls == 0


def test_true_provider_absence_does_not_spend_pipeline_repair_budget(tmp_path: Path) -> None:
    _write_target(tmp_path)
    registry = ProviderRegistry(include_bootstrap=False)
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    queue, task = _task(tmp_path)
    loop.queue = queue
    store = PipelineStore(queue.path)
    store.register_discovery(
        task.task_id,
        "genesis/worker.py",
        {"finding": {"confidence_normalized": 0.9}},
    )
    store.transition(task.task_id, "repair_ready", worker="triage")

    result = SingleAttemptRepairWorker(tmp_path, loop, store).run(store.get(task.task_id))

    assert result["action"] == "pipeline_wait_coding_provider"
    record = store.get(task.task_id)
    assert record is not None
    assert record.stage == "needs_repair"
    assert record.repair_attempts == 0
    current = queue.get(task.task_id)
    assert current is not None
    assert current.state == "paused"
    assert current.attempt_count == 0


def test_coder_wait_checkpoint_is_provider_neutral() -> None:
    assert GenePulse._next_pulse_decision("pipeline_wait_coding_provider", {}) == (
        False,
        "waiting_for_eligible_coding_provider",
    )

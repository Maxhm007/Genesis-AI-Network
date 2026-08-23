from __future__ import annotations

from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.autonomy_pipeline import PipelineStore
from genesis.bounded_autonomy_pipeline import SingleAttemptRepairWorker
from genesis.intelligence_router import IntelligenceRouter
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import BootstrapProvider, ProviderRegistry
from genesis.pulse import GenePulse


class TrackingQwenProvider:
    name = "qwen3-0.6b-genesis-core"

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


def test_qwen_is_selected_when_it_is_the_only_trained_coder(tmp_path: Path) -> None:
    _write_target(tmp_path)
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)

    selected = loop._coding_provider()

    assert selected is qwen
    assert qwen.calls == 0


def test_qwen_is_preferred_over_other_coder_for_genesis_lineage(tmp_path: Path) -> None:
    _write_target(tmp_path)
    qwen = TrackingQwenProvider()
    strong = StrongCodingProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(strong)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)

    selected = loop._coding_provider()

    assert selected is qwen
    assert qwen.calls == 0


def test_router_prefers_qwen_over_bootstrap_for_cognitive_work() -> None:
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(BootstrapProvider())
    registry.register(qwen)
    router = IntelligenceRouter(registry)

    decision = router.select("planning", complexity=0.1)

    assert decision.provider is qwen
    assert decision.reason.startswith("qwen_cognitive_ancestor")


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

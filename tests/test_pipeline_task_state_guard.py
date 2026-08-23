from pathlib import Path

from genesis.autonomy_pipeline import PipelineStore
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.pipeline_task_state_guard import install_pipeline_task_state_guard


def test_paused_task_is_not_reported_as_active_pipeline_work(tmp_path: Path) -> None:
    install_pipeline_task_state_guard()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Develop a capability when its provider becomes available",
        module_id="genesis.coding",
        payload={"source": "genesis.evolution_learning"},
    )
    store = PipelineStore(queue.path)
    store.register_discovery(
        task.task_id,
        "genesis/learned_capabilities.py",
        {"source": "genesis.evolution_learning", "finding": {"confidence_normalized": 0.9}},
    )

    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.hold(task.task_id, "waiting_for_eligible_development_provider")
    store.transition(
        task.task_id,
        "needs_development_revision",
        worker="development",
        feedback="no_non_qwen_coding_provider_available",
    )

    assert queue.get(task.task_id).state == "paused"
    assert store.get(task.task_id).stage == "needs_development_revision"
    assert store.list_active() == []


def test_resumed_task_reenters_active_pipeline_without_data_loss(tmp_path: Path) -> None:
    install_pipeline_task_state_guard()
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        "Resume preserved capability work later",
        module_id="genesis.coding",
        payload={"source": "genesis.evolution_learning"},
    )
    store = PipelineStore(queue.path)
    store.register_discovery(
        task.task_id,
        "genesis/learned_capabilities.py",
        {"source": "genesis.evolution_learning", "finding": {"confidence_normalized": 0.9}},
    )
    queue.transition(task.task_id, "assigned", module_id="genesis.coding")
    queue.transition(task.task_id, "running", module_id="genesis.coding")
    queue.hold(task.task_id, "waiting_for_eligible_development_provider")
    store.transition(task.task_id, "needs_development_revision", worker="development")

    assert store.list_active() == []
    queue.resume(task.task_id)

    active = store.list_active()
    assert [record.task_id for record in active] == [task.task_id]
    assert active[0].stage == "needs_development_revision"

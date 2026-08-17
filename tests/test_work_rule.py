from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.work_rule import GeneWorkRule


def test_gene_keeps_same_issue_after_failure(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    first = queue.create("Fix primary issue", priority=90, max_attempts=5)
    second = queue.create("Fix secondary issue", priority=80)
    rule = GeneWorkRule(tmp_path, "gene-node-2", queue)

    decision1 = rule.decide()
    assert decision1.task_id == first.task_id

    queue.transition(first.task_id, "assigned")
    queue.transition(first.task_id, "running")
    queue.record_failure(first.task_id, "attempt failed", retry_after_seconds=0)

    decision2 = rule.decide()
    assert decision2.task_id == first.task_id
    assert decision2.task_id != second.task_id


def test_gene_moves_on_only_after_resolution(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    first = queue.create("Fix first issue", priority=90)
    second = queue.create("Fix next issue", priority=80)
    rule = GeneWorkRule(tmp_path, "gene-node-3", queue)

    assert rule.decide().task_id == first.task_id
    queue.transition(first.task_id, "assigned")
    queue.transition(first.task_id, "running")
    queue.transition(first.task_id, "review")
    queue.transition(first.task_id, "complete")

    assert rule.decide().task_id == second.task_id


def test_gene_enters_learning_when_no_issue_exists(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    rule = GeneWorkRule(tmp_path, "gene-node-2", queue)

    decision = rule.decide()
    assert decision.mode == "learn_discover"
    assert decision.task_id is None


def test_external_block_can_release_focus(tmp_path: Path) -> None:
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    blocked = queue.create(
        "Needs owner-controlled secret",
        priority=100,
        payload={"external_blocked": True, "external_dependency": "owner secret"},
    )
    actionable = queue.create("Actionable issue", priority=80)
    rule = GeneWorkRule(tmp_path, "gene-node-2", queue)

    decision = rule.decide()
    assert decision.task_id == actionable.task_id
    assert decision.task_id != blocked.task_id

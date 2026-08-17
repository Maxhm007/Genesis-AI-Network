from pathlib import Path

from genesis.automation import GenesisAutomationModule
from genesis.modules.task_queue import PersistentTaskQueue


def test_automation_retries_then_escalates(tmp_path: Path):
    runtime = tmp_path / "runtime"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        "ops:issue-a",
        "Resolve issue A",
        module_id="genesis.coding",
        payload={"task_type": "operational_issue", "issue_key": "issue-a"},
    )
    report = {"issues": [{"issue_key": "issue-a", "title": "Issue A", "status": "open", "owner_action_required": False}]}
    module = GenesisAutomationModule(tmp_path, max_autonomous_attempts=2)

    first = module.evaluate(report)
    second = module.evaluate(report)
    third = module.evaluate(report)

    assert first["decisions"][0]["action"] == "retry_autonomous"
    assert second["decisions"][0]["action"] == "retry_autonomous"
    assert third["decisions"][0]["action"] == "escalate_chatgpt"
    assert third["decisions"][0]["task_id"] == task.task_id


def test_failed_task_escalates_immediately(tmp_path: Path):
    runtime = tmp_path / "runtime"
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    task, _ = queue.create_unique(
        "ops:issue-b",
        "Resolve issue B",
        module_id="genesis.coding",
        payload={"task_type": "operational_issue", "issue_key": "issue-b"},
    )
    queue.transition(task.task_id, "failed")
    module = GenesisAutomationModule(tmp_path, max_autonomous_attempts=2)
    result = module.evaluate({"issues": [{"issue_key": "issue-b", "title": "Issue B", "status": "open", "owner_action_required": False}]})
    assert result["decisions"][0]["action"] == "escalate_chatgpt"


def test_owner_only_issue_is_not_delegated(tmp_path: Path):
    module = GenesisAutomationModule(tmp_path)
    result = module.evaluate({"issues": [{"issue_key": "issue-c", "title": "Signing secret missing", "status": "blocked", "owner_action_required": True}]})
    assert result["decisions"][0]["action"] == "owner_action"
    assert result["escalate_chatgpt"] == 0

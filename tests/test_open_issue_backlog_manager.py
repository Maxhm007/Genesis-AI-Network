from __future__ import annotations

import importlib.util
from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop
from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "autonomous_engineering.py"
    spec = importlib.util.spec_from_file_location("genesis_open_issue_backlog_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _issue(number: int, title: str, body: str = "", labels: tuple[str, ...] = ()) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.test/issues/{number}",
        "labels": [{"name": label} for label in labels],
    }


def test_every_open_issue_class_has_an_explicit_owner():
    module = _load_script()
    cases = [
        (_issue(1, "Genesis Chat: First communication test"), "persistent_channel"),
        (_issue(2, "Action failed", labels=("genesis-action-retry",)), "action_specialist"),
        (_issue(3, "Repair bug", labels=("genesis-autonomous",)), "issue_autorepair_specialist"),
        (_issue(4, "[Genesis Ops] Capability low", "<!-- genesis-ops:abc -->"), "operations_specialist"),
        (_issue(5, "[Genesis Escalation] Capability low"), "operations_escalation"),
        (
            _issue(6, "Independent peer identity", "Treat this as an external-authority / independent-secret provisioning blocker."),
            "external_blocker",
        ),
        (_issue(7, "Build Model Lab", "Develop training and model lineage."), "development"),
        (
            _issue(8, "Bounded challenge", "<!-- genesis-devlab-task -->\nDevLab-Target: genesis/resource.py"),
            "devlab",
        ),
    ]
    for issue, expected in cases:
        result = module.classify_open_issue(issue)
        assert result["kind"] == expected
        assert result["managed"] is True


def test_generic_open_issue_becomes_persistent_multi_generation_work(monkeypatch, tmp_path: Path):
    module = _load_script()
    issue = _issue(60, "Genesis Model Lab", "Develop training, benchmarking, lineage, rollback and routing integration.")
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])

    first = module.ingest_open_issue_backlog(tmp_path)
    assert first["created_count"] == 1
    row = first["issues"][0]
    assert row["kind"] == "development"
    assert row["status"] == "created"

    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.get(row["task_id"])
    assert task is not None
    assert task.payload["task_type"] == "github_issue_development"
    assert task.payload["github_issue_number"] == 60
    assert task.payload["work_generation"] == 1
    assert task.payload["close_github_issue_after_promotion"] is False

    queue.transition(task.task_id, "assigned", module_id=task.module_id)
    queue.transition(task.task_id, "running", module_id=task.module_id)
    queue.transition(task.task_id, "review", module_id=task.module_id)
    queue.transition(task.task_id, "complete", module_id=task.module_id)

    second = module.ingest_open_issue_backlog(tmp_path)
    row2 = second["issues"][0]
    assert row2["status"] == "created"
    task2 = queue.get(row2["task_id"])
    assert task2 is not None
    assert task2.payload["work_generation"] == 2
    assert task2.task_id != task.task_id


def test_devlab_issue_rearms_new_generation_while_issue_remains_open(monkeypatch, tmp_path: Path):
    module = _load_script()
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "resource.py").write_text("VALUE = 1\n", encoding="utf-8")
    issue = _issue(
        109,
        "Genesis challenge: reject ambiguous network telemetry",
        "<!-- genesis-devlab-task -->\nDevLab-Target: genesis/resource.py\n\n**Acceptance:** reject non-booleans.",
    )
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])

    first = module.ingest_open_issue_backlog(tmp_path)
    first_id = first["issues"][0]["task_id"]
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.get(first_id)
    assert task is not None
    assert task.payload["work_generation"] == 1
    queue.transition(task.task_id, "assigned", module_id=task.module_id)
    queue.transition(task.task_id, "running", module_id=task.module_id)
    queue.transition(task.task_id, "review", module_id=task.module_id)
    queue.transition(task.task_id, "complete", module_id=task.module_id)

    second = module.ingest_open_issue_backlog(tmp_path)
    second_id = second["issues"][0]["task_id"]
    task2 = queue.get(second_id)
    assert task2 is not None
    assert second_id != first_id
    assert task2.payload["work_generation"] == 2
    assert task2.payload["close_github_issue_after_promotion"] is True


def test_devlab_issue_is_the_only_backlog_class_that_closes_after_one_validated_promotion(monkeypatch, tmp_path: Path):
    module = _load_script()
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "resource.py").write_text("VALUE = 1\n", encoding="utf-8")
    issue = _issue(
        109,
        "Genesis challenge: reject ambiguous network telemetry",
        "<!-- genesis-devlab-task -->\nDevLab-Target: genesis/resource.py\n\n**Acceptance:** reject non-booleans.",
    )
    monkeypatch.setattr(module, "_github_open_issues", lambda: [issue])
    report = module.ingest_open_issue_backlog(tmp_path)
    task_id = report["issues"][0]["task_id"]
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.get(task_id)
    assert task is not None
    assert task.payload["close_github_issue_after_promotion"] is True
    assert task.payload["target_path"] == "genesis/resource.py"


def test_concrete_github_backlog_work_outranks_background_engineering(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    background, _ = loop.queue.create_unique(
        "background-model-scout",
        "Evaluate a possible replacement model.",
        module_id="genesis.model_scout",
        priority=100,
        payload={"task_type": "model_evaluation"},
    )
    issue_task, _ = loop.queue.create_unique(
        "github-open-issue:60:generation:1",
        "Advance complete resolution of GitHub issue #60.",
        module_id="genesis.self_development",
        priority=90,
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": 60,
            "work_generation": 1,
        },
    )

    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == issue_task.task_id
    assert selected.task_id != background.task_id
    assert loop._selection_trace[-1]["reason"] == "github_issue_backlog_priority"


def test_proactive_workflow_uses_stronger_bounded_issue_coding_runtime():
    workflow = (ROOT / ".github" / "workflows" / "proactive-development.yml").read_text(encoding="utf-8")
    assert "Qwen/Qwen3-1.7B" in workflow
    assert "GENESIS_PROVIDER_MAX_NEW_TOKENS: '768'" in workflow
    assert "genesis-qwen3-1.7b-${{ runner.os }}-py312-v1" in workflow
    assert "genesis/efficient_engineering.py" in workflow


def test_status_workflow_verifies_exact_promotion_before_closing_and_keeps_broad_work_open():
    workflow = (ROOT / ".github" / "workflows" / "open-issue-backlog-status.yml").read_text(encoding="utf-8")
    assert "actions: read" in workflow
    assert "contents: read" in workflow
    assert "issues: write" in workflow
    assert "actions: write" not in workflow
    assert "contents: write" not in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert workflow.index("git merge-base --is-ancestor") < workflow.index("gh issue close")
    assert "close_issue == 'true'" in workflow
    assert "This broader issue remains open" in workflow


def test_github_backlog_blocked_tasks_consume_bounded_retry_budget():
    lifecycle = (ROOT / "genesis" / "task_lifecycle.py").read_text(encoding="utf-8")
    assert '"github_issue_development"' in lifecycle
    assert "BOUNDED_BLOCKED_TASK_TYPES" in lifecycle

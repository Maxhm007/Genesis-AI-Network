import scripts.genesis_teammate as module


def test_execution_task_key_is_stable_for_same_source_issue_across_runs():
    objective = "Autonomous Genesis development task from issue #867: observability work"
    assert module.execution_task_key(objective, "autonomous-867-run-a") == "source-issue-867"
    assert module.execution_task_key(objective, "autonomous-867-run-b") == "source-issue-867"


def test_execution_task_key_falls_back_to_comment_when_no_source_issue():
    assert module.execution_task_key("Owner requested a direct task", "comment-123") == "source-comment-comment-123"


def test_open_development_issues_keeps_direct_team_task_but_skips_source_duplicate(monkeypatch):
    module.CONFIG["workspaces"] = {"nexus": 1000, "forge": 1002}
    rows = [
        {"number": 1029, "title": "[Nexus Task] direct", "body": "<!-- genesis-team-task -->\nDirect task", "labels": []},
        {"number": 1033, "title": "[Nexus Task] duplicate", "body": "<!-- genesis-team-task -->\nAutonomous Genesis development task from issue #867: work", "labels": []},
    ]
    monkeypatch.setattr(module, "paged_get", lambda path: rows)
    issues = module.open_development_issues()
    assert [row["number"] for row in issues] == [1029]


def test_reconcile_legacy_team_tasks_marks_source_duplicates_superseded(monkeypatch):
    module.CONFIG["workspaces"] = {"nexus": 1000}
    issue = {
        "number": 1033,
        "body": "<!-- genesis-team-task -->\nAutonomous Genesis development task from issue #867: work",
        "labels": [{"name": "genesis-autonomous"}],
    }
    calls = []
    monkeypatch.setattr(module, "paged_get", lambda path: [issue])
    monkeypatch.setattr(module, "request", lambda method, path, payload=None: calls.append((method, path, payload)) or ({"number": 867} if method == "GET" else {}))
    monkeypatch.setattr(module, "comment", lambda number, body: None)
    retired = module.reconcile_legacy_team_tasks()
    assert retired == [1033]
    assert ("POST", "/issues/1033/labels", {"labels": ["genesis-superseded"]}) in calls

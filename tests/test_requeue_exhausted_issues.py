from pathlib import Path

import scripts.requeue_exhausted_issues as module
from scripts.requeue_exhausted_issues import (
    ENGINE_PATHS,
    build_successor_body,
    eligible_exhausted_issue,
    engine_generation,
    find_existing_successor,
    pre_repair_failure_after_marker,
    reset_attempt_status,
    rollback_attempt_status,
    successor_marker,
)


def _issue(body: str, labels: list[str], title: str = "[Genesis Task] repair") -> dict:
    return {
        "number": 42,
        "title": title,
        "body": body,
        "labels": [{"name": label} for label in labels],
    }


def test_engine_generation_is_stable_and_content_sensitive(tmp_path: Path):
    assert ".github/workflows/genesis-bounded-repair-worker.yml" in ENGINE_PATHS
    assert ".github/workflows/genesis-sequential-issue-controller.yml" in ENGINE_PATHS
    assert "scripts/requeue_exhausted_issues.py" in ENGINE_PATHS
    assert "genesis/github_issue_cleanup.py" in ENGINE_PATHS
    for relative in ENGINE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")

    first = engine_generation(tmp_path)
    second = engine_generation(tmp_path)
    assert first == second

    tracked = tmp_path / ENGINE_PATHS[0]
    tracked.write_text("changed", encoding="utf-8")
    assert engine_generation(tmp_path) != first


def test_only_exhausted_safe_target_issue_is_requeue_eligible(tmp_path: Path):
    target = tmp_path / "genesis/example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    body = "- **Target:** `genesis/example.py`\n\nFix the bounded defect."

    eligible, target_name = eligible_exhausted_issue(_issue(body, ["genesis-solver-exhausted"]), tmp_path)
    assert eligible is True
    assert target_name == "genesis/example.py"

    assert eligible_exhausted_issue(_issue(body, []), tmp_path)[0] is False
    assert eligible_exhausted_issue(_issue(body, ["genesis-solver-exhausted", "genesis-working"]), tmp_path)[0] is False
    assert eligible_exhausted_issue(
        _issue(body, ["genesis-solver-exhausted", "genesis-superseded"]), tmp_path
    ) == (False, "superseded")


def test_pre_repair_failure_rolls_back_only_the_dispatched_attempt():
    status = (
        "<!-- genesis-oldest-real-issue-solver -->\n"
        "<!-- genesis-solver-attempt:2 -->\n"
        "- Attempt: **2/3**\n"
    )
    rolled_back = rollback_attempt_status(status)
    assert "genesis-solver-attempt:1" in rolled_back
    assert "Attempt: **1/3**" in rolled_back


def test_pre_repair_failure_is_quarantined_only_after_current_generation_marker():
    marker = "<!-- genesis-requeue-engine:current -->"
    failure = "Genesis bounded repair did not promote a verified change (repair status: `worker_failed_before_evidence`)."

    assert pre_repair_failure_after_marker([{"body": failure}], marker) is True
    assert pre_repair_failure_after_marker([{"body": failure}, {"body": marker}], marker) is False
    assert pre_repair_failure_after_marker([{"body": marker}, {"body": failure}], marker) is True


def test_measurement_issues_share_generation_retry_but_protected_targets_do_not(tmp_path: Path):
    protected = tmp_path / "genesis/security.py"
    protected.parent.mkdir(parents=True)
    protected.write_text("VALUE = 1\n", encoding="utf-8")
    ordinary = tmp_path / "genesis/example.py"
    ordinary.write_text("VALUE = 1\n", encoding="utf-8")

    protected_body = "- **Target:** `genesis/security.py`"
    assert eligible_exhausted_issue(_issue(protected_body, ["genesis-solver-exhausted"]), tmp_path) == (False, "protected_target")

    measured_body = "- **Target:** `genesis/example.py`\nThe same comparable benchmark must show measured score improves."
    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (True, "genesis/example.py")


def test_attempt_status_resets_for_new_engine_generation():
    oldest = "<!-- genesis-oldest-real-issue-solver -->\n<!-- genesis-solver-attempt:3 -->\nstate"
    priority = "<!-- genesis-priority-issue-solver -->\n<!-- genesis-priority-solver-attempt:2 -->\nstate"

    assert "genesis-solver-attempt:0" in reset_attempt_status(oldest)
    assert "genesis-priority-solver-attempt:0" in reset_attempt_status(priority)


def test_successor_body_carries_parent_failure_target_and_new_strategy():
    issue = _issue(
        "- **Target:** `genesis/example.py`\n\nOriginal objective.",
        ["genesis-solver-exhausted", "genesis-deferred"],
        title="[Genesis Task] hard repair",
    )
    body = build_successor_body(issue, "engine-abc", "repair status: blocked by invalid candidate")

    assert successor_marker(42) in body
    assert "- **Parent issue:** #42" in body
    assert "- **Target:** `genesis/example.py`" in body
    assert "repair status: blocked by invalid candidate" in body
    assert "Do not repeat the same failed implementation/proposal unchanged" in body
    assert "Sequential Issue Controller remains the only solve/verify/close lane" in body


def test_existing_successor_is_deduplicated_by_parent_marker():
    successor = {
        "number": 43,
        "body": f"{successor_marker(42)}\nfollow-up",
        "html_url": "https://github.test/issues/43",
    }
    assert find_existing_successor([_issue("x", []), successor], 42) == successor


def test_create_successor_handoff_creates_once_then_supersedes_parent(monkeypatch):
    parent = _issue(
        "- **Target:** `genesis/example.py`\n\nOriginal objective.",
        ["genesis-solver-exhausted", "genesis-deferred"],
        title="[Genesis Task] hard repair",
    )
    parent["state"] = "closed"
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        if method == "POST" and path == "/issues":
            return {"number": 43, "html_url": "https://github.test/issues/43", "body": payload["body"]}
        if method == "PATCH" and path == "/issues/42":
            return {"number": 42, "state": "closed"}
        return {}

    monkeypatch.setattr(module, "_request", fake_request)
    result = module.create_successor_handoff(
        "owner/repo",
        "token",
        parent,
        [parent],
        "engine-abc",
        [{"body": "Genesis bounded repair did not promote a verified change; repair status: `blocked`."}],
    )

    assert result["parent"] == 42
    assert result["successor"] == 43
    assert result["created"] is True
    create = next(payload for method, path, payload in calls if method == "POST" and path == "/issues")
    assert create is not None
    assert successor_marker(42) in create["body"]
    assert set(create["labels"]) == {"genesis-task", "genesis-autonomous", "genesis-repair"}
    assert any(method == "POST" and path == "/issues/42/comments" for method, path, _ in calls)
    assert any(method == "PATCH" and path == "/issues/42" for method, path, _ in calls)


def test_create_successor_handoff_reuses_existing_successor(monkeypatch):
    parent = _issue(
        "- **Target:** `genesis/example.py`",
        ["genesis-solver-exhausted", "genesis-deferred"],
    )
    successor = {
        "number": 43,
        "body": f"{successor_marker(42)}\nfollow-up",
        "html_url": "https://github.test/issues/43",
    }
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
        calls.append((method, path, payload))
        return {"number": 42, "state": "closed"} if method == "PATCH" and path == "/issues/42" else {}

    monkeypatch.setattr(module, "_request", fake_request)
    result = module.create_successor_handoff(
        "owner/repo", "token", parent, [parent, successor], "engine-abc", []
    )

    assert result["successor"] == 43
    assert result["created"] is False
    assert not any(method == "POST" and path == "/issues" for method, path, _ in calls)

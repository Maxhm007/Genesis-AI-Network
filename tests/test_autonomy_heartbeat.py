from pathlib import Path


CREATOR = Path(".github/workflows/genesis-basic-loop-test.yml")
SOLVER = Path(".github/workflows/genesis-oldest-issue-solver.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")
WATCHER = Path(".github/workflows/genesis-action-failure-watcher.yml")


def test_issue_creator_has_bounded_five_minute_continuity() -> None:
    text = CREATOR.read_text(encoding="utf-8")

    assert "interval=300" in text
    assert "max_cycles=64" in text
    assert "Start successor detector run" in text
    assert "genesis-basic-loop-test.yml/dispatches" in text
    assert "cancel-in-progress: true" in text


def test_issue_solver_has_independent_bounded_five_minute_continuity() -> None:
    text = SOLVER.read_text(encoding="utf-8")

    assert "interval=300" in text
    assert "max_cycles=64" in text
    assert "Start successor solver run" in text
    assert "genesis-oldest-issue-solver.yml/dispatches" in text
    assert "group: genesis-oldest-real-issue-solver" in text


def test_bounded_worker_cannot_overlap_same_issue() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "group: genesis-bounded-repair-${{ inputs.issue_number }}" in text
    assert "cancel-in-progress: false" in text
    assert "genesis-repair-in-progress" in text


def test_action_failure_watcher_remains_issue_creation_only() -> None:
    text = WATCHER.read_text(encoding="utf-8")

    assert "workflow_run:" in text
    assert "issues: write" in text
    assert "gh issue create" in text
    assert "The watcher does not repair or close issues" in text
    assert "github_issue_autorepair.py" not in text

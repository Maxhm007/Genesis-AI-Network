from pathlib import Path


CREATOR = Path(".github/workflows/genesis-basic-loop-test.yml")
CONTROLLER = Path(".github/workflows/genesis-sequential-issue-controller.yml")
LEGACY_OLDEST = Path(".github/workflows/genesis-oldest-issue-solver.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")
WATCHER = Path(".github/workflows/genesis-action-failure-watcher.yml")


def test_issue_creator_is_intentionally_manual_only_and_inert() -> None:
    text = CREATOR.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "interval=300" not in text
    assert "Start successor detector run" not in text
    assert "genesis-basic-loop-test.yml/dispatches" not in text
    assert "Genesis Tiny Problem Detection Test is disabled." in text


def test_issue_controller_has_independent_scheduled_continuity() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "cron: '*/10 * * * *'" in text
    assert "group: genesis-sequential-issue-controller" in text
    assert "cancel-in-progress: false" in text
    assert "strict sequential mode will not start another issue" in text
    assert "genesis-bounded-repair-worker.yml" in text


def test_legacy_oldest_solver_is_delegate_only() -> None:
    text = LEGACY_OLDEST.read_text(encoding="utf-8")

    assert "delegate-to-sequential-controller" in text
    assert "genesis-sequential-issue-controller.yml" in text
    assert "genesis-bounded-repair-worker.yml" not in text
    assert "Start successor solver run" not in text
    assert "genesis-oldest-issue-solver.yml/dispatches" not in text


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

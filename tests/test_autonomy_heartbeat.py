from pathlib import Path


CREATOR = Path(".github/workflows/genesis-basic-loop-test.yml")
CONTROLLER = Path(".github/workflows/genesis-sequential-issue-controller.yml")
AGENTIC = Path(".github/workflows/genesis-agentic-lab-recovery.yml")
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


def test_agentic_lab_has_scheduled_continuity_and_sequential_is_feeder_only() -> None:
    agentic = AGENTIC.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")

    assert "schedule:" in agentic
    assert "agentic_parallel_dispatch.py" in agentic
    assert "Agentic Lab is the single issue-routing and strategy authority" in controller
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in controller
    assert "issues: write" not in controller


def test_legacy_oldest_solver_is_retired() -> None:
    assert not LEGACY_OLDEST.exists()


def test_bounded_worker_cannot_overlap_same_issue() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "group: genesis-bounded-repair-${{ inputs.issue_number }}" in text
    assert "cancel-in-progress: false" in text
    assert "genesis-repair-in-progress" in text


def test_action_failure_watcher_reconciles_fresh_success_before_detection_retry() -> None:
    text = WATCHER.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "cron: '*/10 * * * *'" in text
    assert "actions: write" in text
    assert "issues: write" in text
    first_fresh = text.index("python scripts/action_failure_fresh_reconcile.py")
    scan = text.index("python scripts/action_failure_watchdog.py --repository")
    second_fresh = text.index("python scripts/action_failure_fresh_reconcile.py", first_fresh + 1)
    retry = text.index("--retry-once")
    assert first_fresh < scan < second_fresh < retry
    assert "gh issue close" not in text
    assert "github_issue_autorepair.py" not in text

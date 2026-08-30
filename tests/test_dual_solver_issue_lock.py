from pathlib import Path


def test_dual_solvers_share_one_issue_lock_without_permanent_assignment():
    oldest = Path(".github/workflows/genesis-oldest-issue-solver.yml").read_text()
    priority = Path(".github/workflows/genesis-priority-issue-solver.yml").read_text()
    worker = Path(".github/workflows/genesis-bounded-repair-worker.yml").read_text()

    assert "group: genesis-bounded-repair-" in worker
    assert "cancel-in-progress: false" in worker
    assert "'genesis-priority-claim'" in oldest
    assert "'genesis-validating'" in oldest
    assert "shared_owner=" in oldest
    assert "another solver already owns the shared reservation" in oldest
    for label in ("genesis-claimed", "genesis-working", "genesis-verifying", "genesis-repair-in-progress", "genesis-validating"):
        assert label in priority
    assert "Priority solver backed off" in priority
    assert "genesis-solver-exhausted" in oldest
    assert "genesis-priority-exhausted" in priority

from pathlib import Path


def test_sequential_controller_owns_one_issue_lock_and_legacy_solvers_are_retired():
    controller = Path(".github/workflows/genesis-sequential-issue-controller.yml").read_text()
    worker = Path(".github/workflows/genesis-bounded-repair-worker.yml").read_text()

    assert "group: genesis-bounded-repair-" in worker
    assert "cancel-in-progress: false" in worker

    assert not Path(".github/workflows/genesis-oldest-issue-solver.yml").exists()
    assert not Path(".github/workflows/genesis-priority-issue-solver.yml").exists()

    for label in (
        "genesis-claimed",
        "genesis-working",
        "genesis-verifying",
        "genesis-repair-in-progress",
        "genesis-validating",
        "genesis-priority-claim",
    ):
        assert label in controller

    assert "active_count=" in controller
    assert "strict sequential mode will not start another issue" in controller
    assert "shared_owner=" in controller
    assert "another worker already owns the shared reservation" in controller
    assert "genesis-solver-exhausted" in controller

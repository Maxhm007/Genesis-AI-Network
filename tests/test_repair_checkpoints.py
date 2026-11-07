from pathlib import Path

from genesis.issue_solver import IssueSolver
from genesis.repair_checkpoints import RepairCheckpointStore, fingerprint


def test_checkpoint_persists_and_limits_identical_attempts(tmp_path: Path):
    key = fingerprint("import_failure", "FAILED tests/test_x.py::test_y\nE   ModuleNotFoundError: yaml")
    first = RepairCheckpointStore(tmp_path)
    for attempt in range(1, 4):
        assert first.reserve(key, "import_failure")
        first.finish(key, "failed", "test_failed")
        assert RepairCheckpointStore(tmp_path).get(key)["attempts"] == attempt
    assert not RepairCheckpointStore(tmp_path).reserve(key, "import_failure")


def test_checkpoint_stops_verified_signature(tmp_path: Path):
    store = RepairCheckpointStore(tmp_path)
    key = fingerprint("syntax_failure", "SyntaxError: broken")
    assert store.reserve(key, "syntax_failure")
    store.finish(key, "verified", "commit-ref")
    assert not store.reserve(key, "syntax_failure")


def test_fingerprint_ignores_pytest_duration():
    a = fingerprint("import_failure", "FAILED tests/test_x.py::test_y - 1.33s\nE   ImportError: bad")
    b = fingerprint("import_failure", "FAILED tests/test_x.py::test_y - 2.84s\nE   ImportError: bad")
    assert a == b


def test_solver_escalates_after_bounded_failures(tmp_path: Path, monkeypatch):
    solver = IssueSolver(tmp_path)
    failure = "FAILED tests/test_x.py::test_y\nE   ImportError: nonexistent"
    monkeypatch.setattr(solver, "run_tests", lambda: (False, failure))
    monkeypatch.setattr(solver, "_provider_proposal", lambda diagnosis: None)
    for _ in range(3):
        assert solver.solve_once().status == "retry_pending_capability"
    assert solver.solve_once().status == "escalation_required"


def test_healthy_tree_skips_checkpoint(tmp_path: Path, monkeypatch):
    solver = IssueSolver(tmp_path)
    monkeypatch.setattr(solver, "run_tests", lambda: (True, "all passed"))
    assert solver.solve_once().status == "healthy"

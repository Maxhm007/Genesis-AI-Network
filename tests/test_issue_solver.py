from pathlib import Path

import pytest

from genesis.issue_solver import Diagnosis, IssueSolver


def test_diagnoses_provider_mode_staleness(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    diagnosis = solver.diagnose(
        "FAILED test_waiting_for_provider ProviderRegistry waiting_for_provider"
    )
    assert diagnosis.category == "provider_mode_expectation"


def test_constitution_failure_is_protected(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    diagnosis = solver.diagnose("Genesis Constitution verification failed: mismatch")
    assert diagnosis.category == "constitution_integrity"


def test_repair_proposal_cannot_touch_constitution(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    with pytest.raises(ValueError, match="not allowed"):
        solver.validate_proposal(
            {
                "title": "bad repair",
                "files": {"GENESIS_CONSTITUTION.md": "changed"},
            }
        )


def test_repair_proposal_cannot_escape_sandbox(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    with pytest.raises(ValueError, match="not allowed"):
        solver.validate_proposal(
            {
                "title": "bad repair",
                "files": {"run_genesis.py": "print('changed')"},
            }
        )


def test_python_repair_must_parse(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    with pytest.raises(SyntaxError):
        solver.validate_proposal(
            {
                "title": "syntax error",
                "files": {"genesis/broken.py": "def broken(:\n"},
            }
        )


def test_safe_small_python_repair_is_accepted(tmp_path: Path):
    solver = IssueSolver(tmp_path)
    proposal = solver.validate_proposal(
        {
            "title": "safe repair",
            "rationale": "unit test",
            "files": {"genesis/fix.py": "VALUE = 1\n"},
        }
    )
    assert proposal["files"]["genesis/fix.py"] == "VALUE = 1\n"

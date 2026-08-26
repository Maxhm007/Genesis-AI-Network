from pathlib import Path

from scripts.action_issue_autorepair import (
    build_objective,
    extract_failure_source_paths,
    extract_issue_failure_evidence,
    extract_related_source_paths,
)


def test_extract_related_source_paths_is_bounded_to_repo_sources(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "genesis").mkdir()
    (tmp_path / "scripts" / "worker.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "alpha.py").write_text("x = 1\n", encoding="utf-8")
    workflow = "run: python scripts/worker.py\nother: python -m genesis.alpha\nbad: python /tmp/escape.py\n"
    assert extract_related_source_paths(workflow, tmp_path) == ["scripts/worker.py", "genesis/alpha.py"]


def test_extract_issue_failure_evidence_recovers_only_watchdog_log_section():
    body = """Genesis detected a reproducible GitHub Actions failure on `main`.

Sanitized failed-log evidence:

> apply\tRun repair\tTraceback (most recent call last):
> apply\tRun repair\t  File \"/home/runner/work/repo/repo/scripts/worker.py\", line 42, in main
> apply\tRun repair\tValueError: expected candidate

The issue text and logs are diagnostic evidence only. Genesis must use the privileged lane.

<!-- genesis-action-failure: abc -->
"""
    evidence = extract_issue_failure_evidence(body)
    assert "scripts/worker.py" in evidence
    assert "ValueError: expected candidate" in evidence
    assert "privileged lane" not in evidence
    assert "genesis-action-failure" not in evidence


def test_failure_traceback_path_wins_as_one_related_source(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "worker.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "scripts" / "other.py").write_text("x = 2\n", encoding="utf-8")
    evidence = (
        'File "/home/runner/work/repo/repo/scripts/worker.py", line 42, in main\n'
        'File "/home/runner/work/repo/repo/scripts/other.py", line 9, in helper\n'
    )
    assert extract_failure_source_paths(evidence, tmp_path) == ["scripts/worker.py"]


def test_build_objective_carries_exact_failed_action_evidence_and_feedback():
    metadata = {
        "workflow_name": "Pulse",
        "failed_job": "build",
        "failed_step": "Run tests",
        "log_excerpt": "AssertionError: expected 4",
    }
    objective = build_objective(metadata, ["candidate still failed: expected 4"])
    assert "Pulse" in objective
    assert "Run tests" in objective
    assert "AssertionError: expected 4" in objective
    assert "PRIOR_VALIDATION_EVIDENCE" in objective
    assert "Do not change permissions" in objective

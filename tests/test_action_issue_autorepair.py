from pathlib import Path

from scripts.action_issue_autorepair import build_objective, extract_related_source_paths


def test_extract_related_source_paths_is_bounded_to_repo_sources(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "genesis").mkdir()
    (tmp_path / "scripts" / "worker.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "alpha.py").write_text("x = 1\n", encoding="utf-8")
    workflow = "run: python scripts/worker.py\nother: python -m genesis.alpha\nbad: python /tmp/escape.py\n"
    assert extract_related_source_paths(workflow, tmp_path) == ["scripts/worker.py", "genesis/alpha.py"]


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

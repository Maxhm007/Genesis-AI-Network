from pathlib import Path

from scripts.github_issue_autorepair import (
    CONTROL_PLANE_FILES,
    allowed_issue_repair_paths,
    build_issue_text,
    candidate_context_paths,
)


def test_explicit_safe_genesis_path_is_prioritized(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "budget.py").write_text("class CycleBudget: pass\n", encoding="utf-8")

    issue = {"title": "Alpha bug", "body": "Please inspect `genesis/alpha.py` for the reported edge case."}
    paths = candidate_context_paths(build_issue_text(issue), tmp_path)

    assert paths[0] == "genesis/alpha.py"


def test_keyword_ranking_prefers_relevant_source(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "budget.py").write_text(
        "class CycleBudget:\n    max_research_items = 5\n",
        encoding="utf-8",
    )

    issue = {"title": "Cycle budget accepts a bad research limit", "body": "Budget validation should reject invalid research values."}
    paths = candidate_context_paths(build_issue_text(issue), tmp_path)

    assert paths[0] == "genesis/budget.py"


def test_control_plane_files_are_excluded_from_issue_context(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    for relative in CONTROL_PLANE_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "genesis" / "health.py").write_text("def health(): return True\n", encoding="utf-8")

    paths = candidate_context_paths("security autonomy validator blockchain", tmp_path)

    assert not (set(paths) & CONTROL_PLANE_FILES)
    assert "genesis/health.py" in paths


def test_issue_repair_scope_allows_only_context_and_conventional_tests():
    allowed = allowed_issue_repair_paths(["genesis/budget.py", "genesis/health.py"])

    assert "genesis/budget.py" in allowed
    assert "tests/test_budget.py" in allowed
    assert "tests/test_health.py" in allowed
    assert "genesis/security.py" not in allowed
    assert ".github/workflows/anything.yml" not in allowed

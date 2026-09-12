from pathlib import Path

import scripts.agentic_strategy_repair as module


def test_agentic_lab_prefers_explicit_safe_scripts_target(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    target = tmp_path / "scripts" / "self_evaluation_dashboard.py"
    target.write_text("def render():\n    return '<nav>'\n", encoding="utf-8")

    issue_text = "Target: `scripts/self_evaluation_dashboard.py`\nAdd an accessible navigation label."

    paths = module._script_aware_context_paths(lambda *_args: ["genesis/other.py"], issue_text, tmp_path, 6)

    assert paths == ["scripts/self_evaluation_dashboard.py"]


def test_agentic_lab_allows_matching_script_regression_test():
    allowed = module._script_aware_allowed_paths(
        lambda paths: set(paths),
        ["scripts/self_evaluation_dashboard.py"],
    )

    assert "scripts/self_evaluation_dashboard.py" in allowed
    assert "tests/test_self_evaluation_dashboard.py" in allowed


def test_agentic_lab_never_allows_protected_script_target(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    target = tmp_path / "scripts" / "secret_guard.py"
    target.write_text("def guard(): return True\n", encoding="utf-8")

    issue_text = "Target: `scripts/secret_guard.py`\nChange the guard."
    paths = module._script_aware_context_paths(lambda *_args: ["genesis/safe.py"], issue_text, tmp_path, 6)

    assert paths == ["genesis/safe.py"]

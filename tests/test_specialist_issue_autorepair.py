from pathlib import Path

import scripts.github_issue_autorepair as base
from scripts.specialist_issue_autorepair import (
    _explicit_safe_script_paths,
    specialist_allowed_paths,
    specialist_context_paths,
)


def _write(root: Path, relative: str, text: str = "VALUE = 1\n") -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_specialist_issue_prioritizes_explicit_script_target_and_companion_test(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/dashboard_navigation_fallback.py")
    _write(tmp_path, "tests/test_dashboard_navigation_fallback.py", "def test_dashboard(): assert True\n")
    _write(tmp_path, "genesis/improvement.py")

    issue_text = (
        "TITLE: [Genesis Repair Follow-up] Dashboard improvement\n"
        "BODY:\n"
        "- **Target:** `scripts/dashboard_navigation_fallback.py`\n\n"
        "### Required next strategy\n"
        "Diagnose the blocker and use a materially different bounded strategy.\n"
    )

    paths = specialist_context_paths(issue_text, tmp_path)

    assert paths[:2] == [
        "scripts/dashboard_navigation_fallback.py",
        "tests/test_dashboard_navigation_fallback.py",
    ]
    assert "genesis/improvement.py" not in paths


def test_protected_script_target_is_not_selected(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/secret_guard.py")

    assert _explicit_safe_script_paths("Target `scripts/secret_guard.py`", tmp_path) == []


def test_specialist_scope_allows_only_target_and_companion_test() -> None:
    allowed = specialist_allowed_paths(["scripts/dashboard_navigation_fallback.py"])

    assert "scripts/dashboard_navigation_fallback.py" in allowed
    assert "tests/test_dashboard_navigation_fallback.py" in allowed
    assert "genesis/security.py" not in allowed

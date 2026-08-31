from __future__ import annotations

import json
from pathlib import Path

from genesis.coding import CodingModule
from genesis.github_issue_capability_builder import GitHubIssueLearnedCapabilityProvider


def _write_versioning(root: Path, *, duplicate: bool = False) -> None:
    target = root / "genesis" / "modules" / "versioning.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "class ModuleVersionManager:\n"
        "    @staticmethod\n"
        "    def should_rollback(before_percent, after_percent, regression_tolerance=0.0):\n"
        "        return after_percent > before_percent - regression_tolerance\n"
    )
    if duplicate:
        body += (
            "\n"
            "def another(before_percent, after_percent, regression_tolerance=0.0):\n"
            "    return after_percent > before_percent - regression_tolerance\n"
        )
    target.write_text(body, encoding="utf-8")


def _issue(*, author: str = "github-actions[bot]", exact: bool = True) -> dict:
    expected = (
        "- **Expected behavior:** return true only when `after_percent < before_percent - regression_tolerance`.\n"
        if exact
        else "- **Expected behavior:** rollback only when the post-change score is lower.\n"
    )
    return {
        "number": 700,
        "title": "[Genesis Detected] Fix reversed rollback comparison",
        "user": {"login": author},
        "body": (
            "Genesis autonomously detected a real logic regression.\n\n"
            "- **Target:** `genesis/modules/versioning.py`\n"
            "- **Observed defect:** `ModuleVersionManager.should_rollback()` uses the wrong comparison direction.\n"
            + expected
            + "- **Verification:** compile the target and pass the full repository test suite before closing.\n"
        ),
    }


def test_machine_detected_issue_builds_exact_expression_repair(tmp_path: Path) -> None:
    _write_versioning(tmp_path)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(),
        CodingModule(tmp_path),
    )

    assert provider is not None
    proposal = json.loads(provider.reason("ignored"))
    rendered = proposal["files"]["genesis/modules/versioning.py"]
    assert "return after_percent < before_percent - regression_tolerance" in rendered
    assert "return after_percent > before_percent - regression_tolerance" not in rendered
    compile(rendered, "genesis/modules/versioning.py", "exec")


def test_user_issue_cannot_use_detected_expression_route(tmp_path: Path) -> None:
    _write_versioning(tmp_path)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(author="Maxhm007"),
        CodingModule(tmp_path),
    )
    assert provider is None


def test_detected_route_requires_exact_expected_expression(tmp_path: Path) -> None:
    _write_versioning(tmp_path)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(exact=False),
        CodingModule(tmp_path),
    )
    assert provider is None


def test_detected_route_rejects_ambiguous_source_line(tmp_path: Path) -> None:
    _write_versioning(tmp_path, duplicate=True)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _issue(),
        CodingModule(tmp_path),
    )
    assert provider is None

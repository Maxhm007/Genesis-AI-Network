from pathlib import Path
from types import SimpleNamespace

import pytest

from genesis.coding import CodingModule
from genesis.system_issue_repair_policy import (
    PRIVILEGE_ANCHOR,
    _ground_requested_issue_context,
    _normalize_with_privileged_scripts,
    _proposal_with_privilege_anchor,
)


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_requested_system_issue_can_ground_in_privileged_script_and_test(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/budget.py", "class CycleBudget:\n    pass\n")
    _write(
        tmp_path,
        "scripts/github_issue_autorepair.py",
        "def validate_issue_candidate():\n"
        "    # semantic issue acceptance evidence before promotion of an autorepair candidate\n"
        "    return 'untrusted issue safeguards'\n",
    )
    _write(
        tmp_path,
        "scripts/action_issue_autorepair.py",
        "def repair_action_failure():\n    return 'action workflow failure'\n",
    )
    _write(
        tmp_path,
        "tests/test_github_issue_autorepair.py",
        "def test_semantic_issue_acceptance():\n    assert True\n",
    )
    module = CodingModule(tmp_path)
    context = ["genesis/budget.py"]
    objective = (
        "Resolve exactly the described software defect.\n"
        "ISSUE_EVIDENCE:\n"
        "TITLE: Autorepair can promote semantic no-op fixes\n"
        "BODY:\n"
        "A previous defect happened in `genesis/budget.py`.\n\n"
        "Required system improvement:\n"
        "- require semantic issue satisfaction and issue-specific acceptance evidence before promotion;\n"
        "- reject formatting/no-op candidates and preserve untrusted-issue safeguards.\n"
    )

    grounded = _ground_requested_issue_context(module, objective, context)

    assert grounded == [
        "scripts/github_issue_autorepair.py",
        "tests/test_github_issue_autorepair.py",
    ]
    assert context == grounded


def test_script_path_requires_privileged_normalization(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="privileged autonomy lane"):
        _normalize_with_privileged_scripts(tmp_path, "scripts/helper.py", allow_privileged=False)

    assert (
        _normalize_with_privileged_scripts(tmp_path, "scripts/helper.py", allow_privileged=True)
        == "scripts/helper.py"
    )


def test_script_proposal_gets_unchanged_privilege_anchor(tmp_path: Path) -> None:
    _write(tmp_path, PRIVILEGE_ANCHOR, "name: Genesis GitHub Issue Autorepair\n")
    executor = SimpleNamespace(root=tmp_path)
    proposal = {
        "title": "Genesis issue repair #273",
        "files": {
            "scripts/github_issue_autorepair.py": "VALUE = 2\n",
            "tests/test_github_issue_autorepair.py": "def test_value(): assert True\n",
        },
    }

    anchored = _proposal_with_privilege_anchor(executor, proposal)

    assert anchored is not proposal
    assert anchored["files"][PRIVILEGE_ANCHOR] == "name: Genesis GitHub Issue Autorepair\n"
    assert proposal["files"].keys() == {
        "scripts/github_issue_autorepair.py",
        "tests/test_github_issue_autorepair.py",
    }


def test_ordinary_genesis_proposal_does_not_gain_privilege_anchor(tmp_path: Path) -> None:
    executor = SimpleNamespace(root=tmp_path)
    proposal = {"title": "normal", "files": {"genesis/alpha.py": "VALUE = 2\n"}}

    assert _proposal_with_privilege_anchor(executor, proposal) is proposal

import subprocess
from pathlib import Path

import pytest

from scripts.github_issue_discovery_strict import require_reproducible_discovery


def _finding() -> dict:
    return {
        "status": "issue_enqueued",
        "target": "genesis/alpha.py",
        "finding": {
            "decision": "issue",
            "summary": "Alpha accepts an invalid value.",
            "acceptance": "Invalid values are rejected before state changes.",
            "evidence": "VALUE = raw_value",
            "confidence_normalized": 0.9,
        },
    }


def _root(tmp_path: Path) -> Path:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = raw_value\n", encoding="utf-8")
    (tmp_path / "tests" / "test_alpha.py").write_text("def test_alpha():\n    assert False\n", encoding="utf-8")
    return tmp_path


def test_publication_requires_a_real_targeted_test_failure(tmp_path: Path):
    root = _root(tmp_path)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="1 failed\n", stderr="")

    validated = require_reproducible_discovery(_finding(), root, runner=runner)

    assert validated["reproduction"]["kind"] == "targeted_test_failure"
    assert validated["reproduction"]["returncode"] == 1
    assert validated["reproduction"]["command"].endswith("tests/test_alpha.py")


def test_publication_rejects_risk_inference_when_target_tests_pass(tmp_path: Path):
    root = _root(tmp_path)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="1 passed\n", stderr="")

    with pytest.raises(ValueError, match="risk inference"):
        require_reproducible_discovery(_finding(), root, runner=runner)


def test_publication_rejects_missing_conventional_target_test(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = raw_value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="conventional target test"):
        require_reproducible_discovery(_finding(), tmp_path)


def test_publication_rejects_pytest_collection_or_infrastructure_errors(tmp_path: Path):
    root = _root(tmp_path)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 5, stdout="no tests ran\n", stderr="")

    with pytest.raises(ValueError, match="normal pytest failure"):
        require_reproducible_discovery(_finding(), root, runner=runner)

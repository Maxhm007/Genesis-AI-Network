from pathlib import Path
import subprocess

from scripts.issue_acceptance_guard import evaluate_candidate


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(args, cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path) -> str:
    _run(tmp_path, "git", "init", "-b", "main")
    _run(tmp_path, "git", "config", "user.name", "Genesis Test")
    _run(tmp_path, "git", "config", "user.email", "genesis-test@example.com")
    _write(tmp_path, "genesis/__init__.py", "")
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n",
    )
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "base")
    return _run(tmp_path, "git", "rev-parse", "HEAD")


def test_acceptance_requires_candidate_test_to_fail_on_old_base(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 2\n",
    )
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "fix alpha")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha returns the wrong value\nBODY:\nRequired fix:\nAlpha must return value 2.",
    )

    assert evidence["status"] == "accepted"
    assert evidence["base_test_returncode"] == 1
    assert evidence["candidate_test_returncode"] == 0
    assert evidence["semantic_files"] == ["genesis/alpha.py"]
    assert "alpha" in evidence["issue_term_overlap"]


def test_acceptance_rejects_production_change_without_regression_test(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "def alpha_value():\n    return 2\n")
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "change without test")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha returns the wrong value\nBODY:\nRequired fix:\nAlpha must return 2.",
    )

    assert evidence["status"] == "rejected"
    assert evidence["reason"] == "no_changed_regression_test"


def test_acceptance_rejects_regression_test_that_already_passes_on_base(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write(tmp_path, "genesis/alpha.py", "# documentation only\ndef alpha_value():\n    return 1\n")
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from genesis.alpha import alpha_value\n\ndef test_alpha_value():\n    assert alpha_value() == 1\n\ndef test_alpha_still_one():\n    assert alpha_value() == 1\n",
    )
    _run(tmp_path, "git", "add", ".")
    _run(tmp_path, "git", "commit", "-m", "format only")

    evidence = evaluate_candidate(
        tmp_path,
        base,
        "TITLE: Alpha semantic defect\nBODY:\nRequired fix:\nChange Alpha behavior.",
    )

    assert evidence["status"] == "rejected"
    assert evidence["reason"] == "python_ast_unchanged_formatting_or_comment_only"

from __future__ import annotations

import subprocess
from pathlib import Path

from genesis.ephemeral_validator import (
    _candidate_changed_paths,
    _candidate_fork_point,
    _protected_paths_match_current_main,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def _commit(root: Path, path: str, text: str, message: str) -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(root, "add", path)
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "validator@example.com")
    _git(root, "config", "user.name", "Validator Test")
    _commit(root, "GENESIS_CONSTITUTION.md", "constitution\n", "base constitution")
    _commit(root, "GENESIS_BLOCK.json", "{}\n", "base block")
    return root


def test_candidate_remains_valid_when_main_advances_in_parallel(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "main")
    _git(root, "checkout", "-b", "candidate")
    candidate = _commit(root, "genesis/feature.py", "VALUE = 1\n", "candidate change")

    _git(root, "checkout", "main")
    main = _commit(root, "genesis/parallel.py", "VALUE = 2\n", "parallel main change")

    assert _candidate_fork_point(root, main, candidate) == base
    assert _candidate_changed_paths(root, base, candidate) == ["genesis/feature.py"]
    assert _protected_paths_match_current_main(root, main, candidate)


def test_candidate_with_unrelated_history_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    main = _git(root, "rev-parse", "main")
    _git(root, "checkout", "--orphan", "unrelated")
    _git(root, "rm", "-rf", ".")
    candidate = _commit(root, "genesis/unrelated.py", "VALUE = 3\n", "unrelated history")

    assert _candidate_fork_point(root, main, candidate) is None


def test_candidate_cannot_diverge_on_protected_identity_files(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _git(root, "checkout", "-b", "candidate")
    candidate = _commit(root, "GENESIS_CONSTITUTION.md", "changed constitution\n", "change protected file")

    _git(root, "checkout", "main")
    main = _commit(root, "genesis/parallel.py", "VALUE = 4\n", "advance main")

    assert not _protected_paths_match_current_main(root, main, candidate)

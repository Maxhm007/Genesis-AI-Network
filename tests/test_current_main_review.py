from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from genesis.current_main_review import (
    _prepare_candidate_on_current_main,
    _restore_exact_candidate,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path, *, conflict_on_main: bool = False):
    root = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    root.mkdir()
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Genesis AI")
    _git(root, "config", "user.email", "genesis-ai@users.noreply.github.com")
    _git(root, "remote", "add", "origin", str(remote))

    target = root / "genesis" / "sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 'base'\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    _git(root, "push", "-u", "origin", "main")

    _git(root, "checkout", "-b", "candidate")
    target.write_text("VALUE = 'candidate'\n", encoding="utf-8")
    _git(root, "add", "genesis/sample.py")
    _git(
        root,
        "commit",
        "-m",
        "Genesis self-development candidate: update sample capability",
    )
    candidate_sha = _git(root, "rev-parse", "HEAD")
    review_ref = f"genesis/review-{candidate_sha[:12]}"
    _git(root, "push", "origin", f"HEAD:refs/heads/{review_ref}")

    _git(root, "checkout", "main")
    current_only = root / "current_main_only.py"
    current_only.write_text("CURRENT_MAIN_ONLY = True\n", encoding="utf-8")
    if conflict_on_main:
        target.write_text("VALUE = 'main-new'\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "advance main independently")
    _git(root, "push", "origin", "main")
    _git(root, "fetch", "origin", "main")

    record = SimpleNamespace(
        candidate_sha=candidate_sha,
        candidate_branch=f"genesis/candidate-{candidate_sha[:12]}",
        review_ref=review_ref,
        target_path="genesis/sample.py",
    )
    worker = SimpleNamespace(root=root)
    return root, worker, record, candidate_sha


def test_stale_candidate_patch_is_reviewed_on_current_main(tmp_path: Path) -> None:
    root, worker, record, candidate_sha = _repo(tmp_path)

    ok, feedback, diff, main_sha = _prepare_candidate_on_current_main(worker, record)

    assert ok is True, feedback
    assert main_sha == _git(root, "rev-parse", "origin/main")
    assert _git(root, "rev-parse", "HEAD") == main_sha
    assert (root / "current_main_only.py").is_file()
    assert (root / "genesis" / "sample.py").read_text(encoding="utf-8") == "VALUE = 'candidate'\n"
    assert _git(root, "diff", "--name-only").splitlines() == ["genesis/sample.py"]
    assert "VALUE = 'candidate'" in diff

    restored, restore_error = _restore_exact_candidate(worker, candidate_sha)
    assert restored is True, restore_error
    assert _git(root, "rev-parse", "HEAD") == candidate_sha
    assert not (root / "current_main_only.py").exists()


def test_current_main_conflict_is_rejected_before_review(tmp_path: Path) -> None:
    _root, worker, record, _candidate_sha = _repo(tmp_path, conflict_on_main=True)

    ok, feedback, diff, _main_sha = _prepare_candidate_on_current_main(worker, record)

    assert ok is False
    assert feedback.startswith("internal_review_current_main_patch_conflict:")
    assert diff == ""

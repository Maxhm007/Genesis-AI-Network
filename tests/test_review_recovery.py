from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from genesis.autonomy_pipeline import DEVELOPMENT_SOURCE, PipelineStore
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.review_recovery import recover_one_orphan_review


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


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    root.mkdir()
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Genesis AI")
    _git(root, "config", "user.email", "genesis-ai@users.noreply.github.com")
    _git(root, "remote", "add", "origin", str(remote))

    target = root / "genesis" / "learned_capabilities.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def register_capability(name, description, evidence, handler):\n"
        "    return (name, description, evidence, handler)\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    _git(root, "push", "-u", "origin", "main")

    _git(root, "checkout", "-b", "candidate")
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT",
            "def _cap(value):\n"
            "    return str(value).strip()\n\n"
            "register_capability(\n"
            "    'bounded_normalizer',\n"
            "    'Normalize one bounded input deterministically.',\n"
            "    'verified external evidence for deterministic normalization',\n"
            "    _cap,\n"
            ")\n\n"
            "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT",
        ),
        encoding="utf-8",
    )
    _git(root, "add", str(target.relative_to(root)))
    _git(
        root,
        "commit",
        "-m",
        "Genesis self-development candidate: Add learned capability bounded_normalizer",
    )
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", f"HEAD:refs/heads/genesis/review-{sha[:12]}")
    _git(root, "checkout", "main")
    _git(root, "fetch", "origin", "main")
    return root, sha


def test_orphaned_genesis_capability_review_is_reconstructed(tmp_path: Path) -> None:
    root, sha = _repo(tmp_path)
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    store = PipelineStore(queue.path)
    coordinator = SimpleNamespace(
        root=root,
        engineering=SimpleNamespace(queue=queue),
        store=store,
    )

    recovered = recover_one_orphan_review(root, coordinator)

    assert recovered is not None
    assert recovered["candidate_sha"] == sha
    assert recovered["target"] == "genesis/learned_capabilities.py"
    task = queue.get(recovered["task_id"])
    assert task is not None
    assert task.state == "review"
    assert task.payload["source"] == DEVELOPMENT_SOURCE
    assert task.payload["task_type"] == "new_capability"
    assert task.payload["capability_key"] == "bounded_normalizer"
    assert task.payload["discovery"]["finding"]["new_capability"] is True
    assert task.payload["discovery"]["finding"]["grounded"] is True

    record = store.get(task.task_id)
    assert record is not None
    assert record.stage == "review_ready"
    assert record.candidate_sha == sha
    assert record.review_ref == f"genesis/review-{sha[:12]}"


def test_non_genesis_review_commit_is_not_recovered(tmp_path: Path) -> None:
    root, _sha = _repo(tmp_path)
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    store = PipelineStore(queue.path)
    coordinator = SimpleNamespace(
        root=root,
        engineering=SimpleNamespace(queue=queue),
        store=store,
    )

    # The genuine Genesis review is deliberately made ineligible so an unrelated
    # branch cannot be accepted merely by matching the review-ref naming pattern.
    _git(root, "push", "origin", "--delete", next(
        line.split()[0].replace("refs/remotes/origin/", "")
        for line in _git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes/origin/genesis/review-").splitlines()
    ))

    _git(root, "checkout", "-b", "untrusted")
    target = root / "genesis" / "learned_capabilities.py"
    target.write_text(target.read_text(encoding="utf-8") + "# unrelated\n", encoding="utf-8")
    _git(root, "add", str(target.relative_to(root)))
    _git(root, "config", "user.email", "someone@example.com")
    _git(root, "commit", "-m", "Not a Genesis candidate")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", f"HEAD:refs/heads/genesis/review-{sha[:12]}")
    _git(root, "checkout", "main")

    assert recover_one_orphan_review(root, coordinator) is None
    assert store.list_active() == []

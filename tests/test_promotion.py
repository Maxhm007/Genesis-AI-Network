from pathlib import Path
import subprocess

import pytest

from genesis.promotion import PromotionManager, make_vote


def git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


def init_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "genesis").mkdir()
    (root / "tests").mkdir()
    (root / "genesis" / "__init__.py").write_text("")
    (root / "GENESIS_CONSTITUTION.md").write_text("immutable\n")
    (root / "GENESIS_BLOCK.json").write_text('{"block_index":0}\n')
    (root / "tests" / "test_base.py").write_text("def test_base():\n    assert True\n")
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Genesis")
    git(root, "config", "user.email", "genesis@localhost")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    return root


def test_two_distinct_approvals_promote_exact_commit(tmp_path):
    root = init_repo(tmp_path)
    git(root, "checkout", "-b", "genesis/candidate-test")
    (root / "genesis" / "feature.py").write_text("VALUE = 1\n")
    (root / "tests" / "test_feature.py").write_text("from genesis.feature import VALUE\ndef test_feature(): assert VALUE == 1\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate")
    candidate = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "main")

    manager = PromotionManager(root, min_approvals=2)
    votes = [
        make_vote("validator-a", candidate, "approve", "tests and scope reviewed"),
        make_vote("validator-b", candidate, "approve", "independent approval"),
    ]
    result = manager.promote(candidate, votes)
    assert result["promoted"] is True
    assert result["main_after"] == candidate
    assert git(root, "rev-parse", "main").stdout.strip() == candidate


def test_one_validator_is_not_enough(tmp_path):
    root = init_repo(tmp_path)
    git(root, "checkout", "-b", "genesis/candidate-test")
    (root / "genesis" / "feature.py").write_text("VALUE = 1\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate")
    candidate = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "main")
    manager = PromotionManager(root, min_approvals=2)
    with pytest.raises(RuntimeError, match="quorum"):
        manager.promote(candidate, [make_vote("validator-a", candidate, "approve", "ok")])


def test_rejection_blocks_promotion(tmp_path):
    root = init_repo(tmp_path)
    git(root, "checkout", "-b", "genesis/candidate-test")
    (root / "genesis" / "feature.py").write_text("VALUE = 1\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate")
    candidate = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "main")
    votes = [
        make_vote("validator-a", candidate, "approve", "ok"),
        make_vote("validator-b", candidate, "approve", "ok"),
        make_vote("validator-c", candidate, "reject", "found risk"),
    ]
    with pytest.raises(RuntimeError, match="quorum"):
        PromotionManager(root, min_approvals=2).promote(candidate, votes)


def test_protected_identity_change_is_blocked(tmp_path):
    root = init_repo(tmp_path)
    git(root, "checkout", "-b", "genesis/candidate-test")
    (root / "GENESIS_CONSTITUTION.md").write_text("changed\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "bad candidate")
    candidate = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "main")
    votes = [
        make_vote("validator-a", candidate, "approve", "ok"),
        make_vote("validator-b", candidate, "approve", "ok"),
    ]
    with pytest.raises(RuntimeError, match="protected"):
        PromotionManager(root, min_approvals=2).promote(candidate, votes)

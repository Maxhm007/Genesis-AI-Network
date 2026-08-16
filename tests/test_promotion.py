from pathlib import Path
import subprocess

import pytest

from genesis.promotion import PromotionManager, generate_validator_keypair, make_signed_vote


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


def add_candidate(root: Path, protected: bool = False) -> str:
    git(root, "checkout", "-b", "genesis/candidate-test")
    if protected:
        (root / "GENESIS_CONSTITUTION.md").write_text("changed\n")
    else:
        (root / "genesis" / "feature.py").write_text("VALUE = 1\n")
        (root / "tests" / "test_feature.py").write_text("from genesis.feature import VALUE\ndef test_feature(): assert VALUE == 1\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate")
    candidate = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "checkout", "main")
    return candidate


def validator_set():
    a_priv, a_pub = generate_validator_keypair()
    b_priv, b_pub = generate_validator_keypair()
    c_priv, c_pub = generate_validator_keypair()
    trusted = {"validator-a": a_pub, "validator-b": b_pub, "validator-c": c_pub}
    return (a_priv, b_priv, c_priv), trusted


def test_two_signed_approvals_promote_exact_commit(tmp_path):
    root = init_repo(tmp_path)
    candidate = add_candidate(root)
    (a, b, _), trusted = validator_set()
    votes = [
        make_signed_vote(a, "validator-a", candidate, "approve", "reviewed"),
        make_signed_vote(b, "validator-b", candidate, "approve", "independent review"),
    ]
    result = PromotionManager(root, trusted, min_approvals=2).promote(candidate, votes)
    assert result["promoted"] is True
    assert result["main_after"] == candidate


def test_one_signed_validator_is_not_enough(tmp_path):
    root = init_repo(tmp_path)
    candidate = add_candidate(root)
    (a, _, _), trusted = validator_set()
    with pytest.raises(RuntimeError, match="quorum"):
        PromotionManager(root, trusted, 2).promote(
            candidate, [make_signed_vote(a, "validator-a", candidate, "approve", "ok")]
        )


def test_signed_rejection_blocks_promotion(tmp_path):
    root = init_repo(tmp_path)
    candidate = add_candidate(root)
    (a, b, c), trusted = validator_set()
    votes = [
        make_signed_vote(a, "validator-a", candidate, "approve", "ok"),
        make_signed_vote(b, "validator-b", candidate, "approve", "ok"),
        make_signed_vote(c, "validator-c", candidate, "reject", "found risk"),
    ]
    with pytest.raises(RuntimeError, match="quorum"):
        PromotionManager(root, trusted, 2).promote(candidate, votes)


def test_fake_signature_does_not_count(tmp_path):
    root = init_repo(tmp_path)
    candidate = add_candidate(root)
    (a, b, _), trusted = validator_set()
    fake = make_signed_vote(a, "validator-b", candidate, "approve", "forged identity")
    good = make_signed_vote(a, "validator-a", candidate, "approve", "ok")
    with pytest.raises(RuntimeError, match="quorum"):
        PromotionManager(root, trusted, 2).promote(candidate, [good, fake])


def test_protected_identity_change_is_blocked(tmp_path):
    root = init_repo(tmp_path)
    candidate = add_candidate(root, protected=True)
    (a, b, _), trusted = validator_set()
    votes = [
        make_signed_vote(a, "validator-a", candidate, "approve", "ok"),
        make_signed_vote(b, "validator-b", candidate, "approve", "ok"),
    ]
    with pytest.raises(RuntimeError, match="protected"):
        PromotionManager(root, trusted, 2).promote(candidate, votes)

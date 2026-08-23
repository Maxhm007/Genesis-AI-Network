from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from genesis.model_training_dataset import GenesisTrainingDatasetBuilder, sha256_file


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=merged,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Owner")
    _git(repo, "config", "user.email", "owner@example.test")
    (repo / "genesis").mkdir()
    (repo / "tests").mkdir()
    (repo / "network").mkdir()
    (repo / "genesis" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "genesis/sample.py")
    _git(repo, "commit", "-m", "Initial owner code")
    return repo


def _actor_env(actor: str) -> dict[str, str] | None:
    if actor == "source":
        return {
            "GIT_AUTHOR_NAME": "Genesis AI",
            "GIT_AUTHOR_EMAIL": "genesis-ai@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "Genesis AI",
            "GIT_COMMITTER_EMAIL": "genesis-ai@users.noreply.github.com",
        }
    if actor == "staged":
        return {
            "GIT_AUTHOR_NAME": "Genesis AI",
            "GIT_AUTHOR_EMAIL": "genesis-ai@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "Genesis Promotion Stager",
            "GIT_COMMITTER_EMAIL": "genesis-promotion@users.noreply.github.com",
        }
    if actor == "owner":
        return None
    raise ValueError(actor)


def _commit(
    repo: Path,
    *,
    message: str,
    actor: str,
    files: dict[str, str],
) -> str:
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", *files.keys())
    _git(repo, "commit", "-m", message, env=_actor_env(actor))
    return _git(repo, "rev-parse", "HEAD")


def _changed_files(repo: Path, commit: str) -> list[str]:
    output = _git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit)
    return sorted(line for line in output.splitlines() if line)


def _validation_row(repo: Path, commit: str, *, marker: str = "a", run: str = "100") -> dict:
    return {
        "block_hash": marker * 64,
        "changed_files": _changed_files(repo, commit),
        "height": 1,
        "payload_hash": "f" * 64,
        "payload_type": "validated_update",
        "previous_hash": "e" * 64,
        "producer": "genesis-independent-validator-gate",
        "timestamp": "2026-08-23T00:00:00+00:00",
        "validated_commit": commit,
        "validation_run_id": run,
    }


def _write_blockchain(repo: Path, rows: list[dict]) -> None:
    path = repo / "network" / "blockchain.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_includes_validated_genesis_candidate_already_on_main(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    autonomous = _commit(
        repo,
        message="Genesis self-development candidate: Add bounded selection",
        actor="source",
        files={"genesis/sample.py": "VALUE = 2\n"},
    )
    owner = _commit(
        repo,
        message="Owner infrastructure change",
        actor="owner",
        files={"genesis/sample.py": "VALUE = 3\n"},
    )
    _write_blockchain(
        repo,
        [
            _validation_row(repo, autonomous, marker="a", run="101"),
            _validation_row(repo, owner, marker="b", run="102"),
        ],
    )

    manifest = GenesisTrainingDatasetBuilder(repo).build(output_name="genesis.jsonl")
    dataset = repo / "runtime" / "model_datasets" / "genesis.jsonl"
    row = json.loads(dataset.read_text(encoding="utf-8").strip())

    assert manifest["example_count"] == 1
    assert manifest["included_promoted_commits"] == [autonomous]
    assert manifest["excluded_by_reason"]["not_genesis_autonomous_candidate"] == 1
    assert row["provenance"]["validated_source_commit"] == autonomous
    assert row["provenance"]["promoted_commit"] == autonomous
    assert row["provenance"]["promotion_mapping"] == "validated_commit_is_current_head_ancestor"
    assert row["provenance"]["classification"] == "genesis_autonomous_validated_promotion"
    assert "Genesis self-development candidate" in row["prompt"]
    assert "VALUE = 2" in row["response"]
    assert sha256_file(dataset) == manifest["dataset_sha256"]
    assert manifest["capability_claim"].startswith("none")


def test_validated_source_candidate_maps_to_patch_identical_staged_main_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "genesis/candidate-test")
    source = _commit(
        repo,
        message="Genesis self-development candidate: Rebased capability",
        actor="source",
        files={"genesis/sample.py": "VALUE = 20\n"},
    )

    _git(repo, "checkout", "main")
    assert _git(repo, "rev-parse", "HEAD") == base
    _commit(
        repo,
        message="Unrelated owner change",
        actor="owner",
        files={"tests/test_unrelated.py": "def test_unrelated():\n    assert True\n"},
    )
    committer_env = {
        "GIT_COMMITTER_NAME": "Genesis Promotion Stager",
        "GIT_COMMITTER_EMAIL": "genesis-promotion@users.noreply.github.com",
    }
    _git(repo, "cherry-pick", source, env=committer_env)
    promoted = _git(repo, "rev-parse", "HEAD")
    assert promoted != source
    _write_blockchain(repo, [_validation_row(repo, source, marker="c", run="103")])

    collection = GenesisTrainingDatasetBuilder(repo).collect()

    assert collection.included_commits == (promoted,)
    assert len(collection.examples) == 1
    provenance = collection.examples[0]["provenance"]
    assert provenance["validated_source_commit"] == source
    assert provenance["promoted_commit"] == promoted
    assert provenance["promotion_mapping"] == "stable_patch_id+message+files+promotion_identity"
    assert provenance["source_committer_name"] == "Genesis AI"
    assert provenance["promoted_committer_name"] == "Genesis Promotion Stager"
    assert provenance["stable_patch_id"]


def test_unvalidated_genesis_commit_is_not_training_data(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(
        repo,
        message="Genesis self-development candidate: Unvalidated work",
        actor="source",
        files={"genesis/sample.py": "VALUE = 9\n"},
    )
    owner = _commit(
        repo,
        message="Owner validated change",
        actor="owner",
        files={"genesis/sample.py": "VALUE = 10\n"},
    )
    _write_blockchain(repo, [_validation_row(repo, owner)])

    with pytest.raises(RuntimeError, match="no provenance-qualified"):
        GenesisTrainingDatasetBuilder(repo).build(output_name="genesis.jsonl")


def test_validated_genesis_candidate_without_promotion_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "orphan-work")
    orphan = _commit(
        repo,
        message="Genesis self-development candidate: Branch-only work",
        actor="source",
        files={"genesis/sample.py": "VALUE = 7\n"},
    )
    _git(repo, "checkout", "main")
    assert _git(repo, "rev-parse", "HEAD") == base
    _write_blockchain(repo, [_validation_row(repo, orphan)])

    collection = GenesisTrainingDatasetBuilder(repo).collect()

    assert collection.examples == ()
    assert collection.excluded_by_reason["validated_candidate_not_promoted_to_current_head"] == 1


def test_mixed_workflow_or_config_commit_is_outside_training_scope(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    commit = _commit(
        repo,
        message="Genesis self-development candidate: Unsafe mixed scope",
        actor="source",
        files={
            "genesis/sample.py": "VALUE = 4\n",
            ".github/workflows/example.yml": "name: example\n",
        },
    )
    _write_blockchain(repo, [_validation_row(repo, commit)])

    collection = GenesisTrainingDatasetBuilder(repo).collect()

    assert collection.examples == ()
    assert collection.excluded_by_reason["outside_bounded_python_training_scope"] == 1


def test_blockchain_changed_files_must_match_commit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    commit = _commit(
        repo,
        message="Genesis self-development candidate: Exact evidence",
        actor="source",
        files={"genesis/sample.py": "VALUE = 5\n"},
    )
    row = _validation_row(repo, commit)
    row["changed_files"] = ["genesis/not-the-real-file.py"]
    _write_blockchain(repo, [row])

    collection = GenesisTrainingDatasetBuilder(repo).collect()

    assert collection.examples == ()
    assert collection.excluded_by_reason["validation_changed_files_mismatch"] == 1


def test_malformed_blockchain_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "network" / "blockchain.jsonl").write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="blockchain line 1"):
        GenesisTrainingDatasetBuilder(repo).collect()


def test_dataset_artifacts_are_deterministic_and_not_overwritten(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    commit = _commit(
        repo,
        message="Genesis self-development candidate: Deterministic data",
        actor="source",
        files={"genesis/sample.py": "VALUE = 6\n"},
    )
    _write_blockchain(repo, [_validation_row(repo, commit)])
    builder = GenesisTrainingDatasetBuilder(repo)

    first = builder.build(output_name="genesis.jsonl")
    second = builder.build(output_name="genesis.jsonl")
    assert first == second

    dataset = repo / "runtime" / "model_datasets" / "genesis.jsonl"
    dataset.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        builder.build(output_name="genesis.jsonl")


def test_manifest_binds_blockchain_and_dataset_hashes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    commit = _commit(
        repo,
        message="Genesis self-development candidate: Bind provenance",
        actor="source",
        files={"genesis/sample.py": "VALUE = 8\n"},
    )
    _write_blockchain(repo, [_validation_row(repo, commit)])

    manifest = GenesisTrainingDatasetBuilder(repo).build(output_name="genesis.jsonl")
    manifest_path = repo / "runtime" / "model_datasets" / "genesis.jsonl.manifest.json"
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert persisted == manifest
    assert persisted["blockchain_sha256"] == hashlib.sha256(
        (repo / "network" / "blockchain.jsonl").read_bytes()
    ).hexdigest()
    assert persisted["dataset_sha256"] == sha256_file(repo / "runtime" / "model_datasets" / "genesis.jsonl")

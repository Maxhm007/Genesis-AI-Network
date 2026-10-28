import hashlib
import json

import pytest
from scripts.prepare_genesis_training_holdout import prepare


def dataset(tmp_path, count):
    path = tmp_path / "verified.jsonl"
    rows = [{"prompt": "task", "response": "patch", "provenance": {
        "classification": "genesis_autonomous_validated_promotion",
        "promoted_commit": f"{i:040x}", "stable_patch_id": f"{i+1000:040x}",
    }} for i in range(count)]
    content = "".join(json.dumps(row) + "\n" for row in rows).encode()
    path.write_bytes(content)
    path.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
        "dataset_sha256": hashlib.sha256(content).hexdigest(), "example_count": count
    }))
    return path


def test_six_examples_cannot_start_training(tmp_path):
    path = dataset(tmp_path, 6)
    result = prepare(path)
    assert result["status"] == "insufficient_examples"
    assert not list(tmp_path.glob("*.train.jsonl"))
    assert result["training_started"] is False


def test_thirty_examples_create_disjoint_heldout_data(tmp_path):
    path = dataset(tmp_path, 30)
    result = prepare(path)
    assert result["status"] == "holdout_ready"
    assert result["train_examples"] == 24
    assert result["holdout_examples"] == 6
    a = [json.loads(x) for x in (tmp_path / "verified.train.jsonl").read_text().splitlines()]
    b = [json.loads(x) for x in (tmp_path / "verified.holdout.jsonl").read_text().splitlines()]
    assert {x["provenance"]["promoted_commit"] for x in a}.isdisjoint(
        {x["provenance"]["promoted_commit"] for x in b})


def test_modified_dataset_fails_closed(tmp_path):
    path = dataset(tmp_path, 6)
    path.write_text(path.read_text() + "tampered")
    with pytest.raises(ValueError, match="checksum"):
        prepare(path)

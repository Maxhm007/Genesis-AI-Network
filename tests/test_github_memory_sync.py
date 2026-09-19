from __future__ import annotations

import json
from pathlib import Path

from genesis.memory import GenesisMemory, MemoryStore
from scripts import github_memory_sync
from scripts import record_verified_decision_memory
from scripts import record_verified_repair_memory


def test_verified_memory_marker_round_trip():
    payload = {
        "schema": "genesis-memory-v1",
        "record": {"memory_id": "memory-test"},
        "integrity_sha256": "abc",
    }
    marker = github_memory_sync.encode_memory_marker(payload)
    assert github_memory_sync.decode_memory_marker(marker) == payload


def test_only_trusted_repository_authors_or_actions_bot_can_seed_memory():
    assert github_memory_sync.trusted_memory_comment(
        {"author_association": "OWNER", "user": {"login": "owner"}}
    )
    assert github_memory_sync.trusted_memory_comment(
        {"author_association": "NONE", "user": {"login": "github-actions[bot]"}}
    )
    assert not github_memory_sync.trusted_memory_comment(
        {"author_association": "NONE", "user": {"login": "random-user"}}
    )


def test_verified_repair_record_is_portable_and_importable(tmp_path: Path, monkeypatch):
    evidence = {
        "provider": "qwen-test",
        "diagnosis": {"category": "parser_bug", "summary": "Boolean coercion was too permissive."},
        "repair_memory": [
            {"provider": "qwen-test", "outcome": "tests_failed", "validation": "one focused assertion failed"}
        ],
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    calls = []

    def fake_api(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/829":
            return {"number": 829, "title": "Reject bool issue numbers"}
        if method == "GET" and path == "/issues/829/comments?per_page=100":
            return []
        if method == "POST" and path == "/labels":
            return {"name": "genesis-memory"}
        if method == "POST" and path == "/issues/829/labels":
            return {"labels": [{"name": "genesis-memory"}]}
        if method == "POST" and path == "/issues/829/comments":
            return {"id": 1}
        raise AssertionError((method, path))

    monkeypatch.setattr(record_verified_repair_memory, "_api", fake_api)

    result = record_verified_repair_memory.record(
        "owner/repo",
        "token",
        issue_number=829,
        target="genesis/github_issue_authority_reconciler.py",
        candidate_sha="a" * 40,
        promoted_sha="b" * 40,
        worker_run="35439082677",
        evidence_path=evidence_path,
        root=tmp_path,
    )

    assert result["status"] == "recorded"
    posted = [
        payload["body"]
        for method, path, payload in calls
        if method == "POST" and path == "/issues/829/comments"
    ][0]
    portable = github_memory_sync.decode_memory_marker(posted)
    assert portable is not None

    other = MemoryStore(tmp_path / "other.sqlite3")
    imported = other.import_portable(portable)
    assert imported.state == "validated"
    assert imported.metadata["provider"] == "qwen-test"
    assert imported.metadata["failed_approaches"][0]["outcome"] == "tests_failed"


def test_recorded_repair_memory_redacts_sensitive_failed_validation(tmp_path: Path):
    memory = GenesisMemory(tmp_path)
    item = memory.remember_verified_repair(
        issue_number=1,
        issue_title="Repair",
        target="genesis/example.py",
        problem_class="test",
        root_cause="bounded failure",
        promoted_sha="b" * 40,
        candidate_sha="a" * 40,
        worker_run="1",
        provider="qwen",
        failed_approaches=[
            {"provider": "qwen", "outcome": "failed", "validation": "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz123456"}
        ],
    )
    assert item.metadata["failed_approaches"] == [{"outcome": "redacted_sensitive_validation"}]



def test_sync_query_is_scoped_to_memory_label():
    source = Path(__file__).resolve().parents[1] / "scripts" / "github_memory_sync.py"
    text = source.read_text(encoding="utf-8")
    assert "label:genesis-verified label:genesis-memory" in text



def test_hydration_keeps_newest_knowledge_key_current(tmp_path: Path):
    source = GenesisMemory(tmp_path / "source")
    first = source.remember_verified_decision(
        decision_id="routing-policy",
        topic="Routing policy",
        rationale="Use the older routing rule.",
        source_ref="issue:1",
        evidence={"version": 1},
    )
    first_payload = source.store.portable_payload(first.memory_id)

    second = source.remember_verified_decision(
        decision_id="routing-policy",
        topic="Routing policy",
        rationale="Use the newer verified routing rule.",
        source_ref="issue:2",
        evidence={"version": 2},
    )
    second_payload = source.store.portable_payload(second.memory_id)

    target = GenesisMemory(tmp_path / "target")
    result = github_memory_sync.hydrate_payloads(target, [first_payload, second_payload])

    assert result["ignored"] == 0
    assert target.store.get(second.memory_id).state == "validated"
    assert target.store.get(first.memory_id).state == "superseded"
    recalled = target.recall("routing policy")
    assert any(row["memory_id"] == second.memory_id for row in recalled)
    assert all(row["memory_id"] != first.memory_id for row in recalled)


def test_verified_architecture_decision_is_recorded_as_portable_memory(tmp_path: Path, monkeypatch):
    calls = []

    def fake_api(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/865":
            return {
                "number": 865,
                "state": "closed",
                "labels": [{"name": "genesis-verified"}],
            }
        if method == "GET" and path == "/issues/865/comments?per_page=100":
            return []
        if method == "POST" and path == "/issues/865/comments":
            return {"id": 5}
        raise AssertionError((method, path))

    monkeypatch.setattr(record_verified_decision_memory, "_api", fake_api)
    monkeypatch.setattr(record_verified_decision_memory, "_ensure_memory_label", lambda *args: None)

    result = record_verified_decision_memory.record_decision(
        "owner/repo",
        "token",
        issue_number=865,
        decision_id="one-root-authority",
        topic="Issue family authority",
        rationale="Keep one authoritative root issue across retries.",
        evidence={"full_suite_passed": True},
        root=tmp_path,
    )

    assert result["status"] == "recorded"
    posted = [
        payload["body"]
        for method, path, payload in calls
        if method == "POST" and path == "/issues/865/comments"
    ][0]
    portable = github_memory_sync.decode_memory_marker(posted)
    assert portable["record"]["memory_type"] == "decision"
    assert portable["record"]["metadata"]["decision_id"] == "one-root-authority"

from pathlib import Path

import pytest

from genesis.memory import GenesisMemory, MemoryStore


def test_candidate_memory_not_recalled_by_default(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    item = store.add(
        memory_type="semantic",
        topic="longevity evidence",
        content="candidate claim",
        source_type="test",
        source_ref="candidate-1",
    )
    assert item.state == "candidate"
    assert store.retrieve("longevity evidence") == []


def test_validated_memory_requires_evidence(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    item = store.add(
        memory_type="procedural",
        topic="coding safety",
        content="run tests before promotion",
        source_type="test",
        source_ref="lesson-1",
    )
    with pytest.raises(ValueError, match="validation evidence"):
        store.transition(item.memory_id, "validated")
    validated = store.transition(item.memory_id, "validated", evidence={"result": "pass"})
    assert validated.state == "validated"
    recalled = store.retrieve("coding safety")
    assert recalled and recalled[0].memory_id == validated.memory_id


def test_runtime_event_is_trusted_observation_and_persists(tmp_path: Path):
    memory = GenesisMemory(tmp_path)
    item = memory.remember_event(topic="coding failure", content="provider returned malformed JSON", source_ref="run-1", success=False)
    reopened = GenesisMemory(tmp_path)
    restored = reopened.store.get(item.memory_id)
    assert restored is not None
    assert restored.state == "validated"
    assert restored.memory_type == "episodic"
    assert restored.metadata["success"] is False


def test_retrieval_prefers_relevant_memory(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    a = store.add(memory_type="procedural", topic="coding pytest", content="run pytest before commit", source_type="test", source_ref="a", state="validated", confidence=1, importance=1)
    store.add(memory_type="semantic", topic="biology aging", content="cellular senescence", source_type="test", source_ref="b", state="validated", confidence=1, importance=1)
    result = store.retrieve("coding pytest", limit=1)
    assert result[0].memory_id == a.memory_id



def test_memory_rejects_sensitive_material(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    with pytest.raises(ValueError, match="sensitive material"):
        store.add(
            memory_type="semantic",
            topic="credential",
            content="api_key=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            source_type="test",
            source_ref="secret-1",
        )


def test_portable_validated_memory_round_trip(tmp_path: Path):
    source = MemoryStore(tmp_path / "source.sqlite3")
    candidate = source.add(
        memory_type="repair",
        topic="parser repair",
        content="Prefer the validated bounded parser fix.",
        source_type="verified_github_repair",
        source_ref="issue:1:commit:abc",
        metadata={"knowledge_key": "repair:parser"},
    )
    validated = source.transition(candidate.memory_id, "validated", evidence={"full_suite_passed": True})
    payload = source.portable_payload(validated.memory_id)

    target = MemoryStore(tmp_path / "target.sqlite3")
    imported = target.import_portable(payload)

    assert imported.state == "validated"
    assert imported.memory_id == validated.memory_id
    assert target.retrieve("parser repair")[0].memory_id == validated.memory_id


def test_portable_memory_integrity_failure_is_rejected(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    candidate = store.add(
        memory_type="decision",
        topic="authority",
        content="Keep one issue root authoritative.",
        source_type="test",
        source_ref="d1",
    )
    validated = store.transition(candidate.memory_id, "validated", evidence={"verified": True})
    payload = store.portable_payload(validated.memory_id)
    payload["record"]["content"] = "tampered"

    with pytest.raises(ValueError, match="integrity"):
        MemoryStore(tmp_path / "other.sqlite3").import_portable(payload)


def test_new_verified_memory_supersedes_same_knowledge_key(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    first = store.add(
        memory_type="repair",
        topic="route parser",
        content="First verified fix.",
        source_type="test",
        source_ref="one",
        metadata={"knowledge_key": "repair:route"},
    )
    first = store.transition(first.memory_id, "validated", evidence={"run": 1})
    second = store.add(
        memory_type="repair",
        topic="route parser",
        content="Newer verified fix.",
        source_type="test",
        source_ref="two",
        metadata={"knowledge_key": "repair:route"},
    )
    second = store.transition(second.memory_id, "validated", evidence={"run": 2})

    changed = store.supersede_knowledge_key(
        "repair:route",
        keep_memory_id=second.memory_id,
        evidence={"replacement_memory_id": second.memory_id},
    )

    assert changed == 1
    assert store.get(first.memory_id).state == "superseded"
    assert [item.memory_id for item in store.retrieve("route parser")] == [second.memory_id]


def test_memory_retention_is_bounded_and_prefers_discarding_rejected(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    rejected_ids = []
    for index in range(105):
        item = store.add(
            memory_type="episodic",
            topic=f"event {index}",
            content=f"bounded event {index}",
            source_type="test",
            source_ref=str(index),
        )
        if index < 10:
            store.transition(item.memory_id, "rejected", evidence={"reason": "test"})
            rejected_ids.append(item.memory_id)

    removed = store.prune(max_items=100)

    assert removed == 5
    assert store.stats()["total"] == 100
    assert all(store.get(memory_id) is None for memory_id in rejected_ids[:5])

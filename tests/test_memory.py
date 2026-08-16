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

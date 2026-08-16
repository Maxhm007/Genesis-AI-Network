from pathlib import Path

import pytest

from genesis.self_learning import SelfLearningStore


def test_candidate_lesson_survives_reopen(tmp_path: Path):
    path = tmp_path / "learning.sqlite3"
    store = SelfLearningStore(path)
    lesson = store.add_candidate(
        source_type="research_review",
        source_ref="task-1",
        topic="longevity",
        lesson="candidate finding",
        evidence={"source": "test"},
        confidence=0.4,
    )
    reopened = SelfLearningStore(path)
    restored = reopened.get(lesson.lesson_id)
    assert restored is not None
    assert restored.state == "candidate"
    assert restored.lesson == "candidate finding"


def test_candidate_deduplicates_by_source(tmp_path: Path):
    store = SelfLearningStore(tmp_path / "learning.sqlite3")
    a = store.add_candidate(source_type="benchmark", source_ref="run-1", topic="reasoning", lesson="first")
    b = store.add_candidate(source_type="benchmark", source_ref="run-1", topic="reasoning", lesson="second")
    assert a.lesson_id == b.lesson_id
    assert len(store.list()) == 1


def test_validation_requires_separate_evidence(tmp_path: Path):
    store = SelfLearningStore(tmp_path / "learning.sqlite3")
    lesson = store.add_candidate(source_type="review", source_ref="x", topic="t", lesson="candidate")
    with pytest.raises(ValueError, match="validation evidence"):
        store.transition(lesson.lesson_id, "validated")
    validated = store.transition(lesson.lesson_id, "validated", validation_evidence={"reviewer": "independent", "result": "pass"})
    assert validated.state == "validated"
    assert validated.evidence["validation"]["result"] == "pass"

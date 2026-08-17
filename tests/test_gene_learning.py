from pathlib import Path

import pytest

from genesis.gene_learning import GeneLearningEngine


def test_genes_keep_separate_learning_stores(tmp_path: Path):
    gene2 = GeneLearningEngine(tmp_path, "gene-node-2")
    gene3 = GeneLearningEngine(tmp_path, "gene-node-3")

    lesson = gene2.add_candidate(
        source_type="experiment",
        source_ref="exp-2-1",
        topic="routing",
        lesson="Provider A performed better on this task family.",
        evidence={"score": 0.8},
        confidence=0.8,
    )

    assert gene2.store.get(lesson.lesson_id) is not None
    assert gene3.store.get(lesson.lesson_id) is None
    assert gene2.status()["store"] != gene3.status()["store"]


def test_only_validated_lessons_can_be_shared(tmp_path: Path):
    gene2 = GeneLearningEngine(tmp_path, "gene-node-2")
    lesson = gene2.add_candidate(
        source_type="benchmark",
        source_ref="bench-1",
        topic="coding",
        lesson="A bounded repair strategy improved the measured benchmark.",
        evidence={"benchmark": "local"},
        confidence=0.9,
    )

    with pytest.raises(ValueError):
        gene2.share_validated(lesson.lesson_id)

    validated = gene2.validate(lesson.lesson_id, {"tests": "passed", "validator": "independent"})
    packet = gene2.share_validated(validated.lesson_id)
    assert packet["provenance"]["learning_state"] == "validated"


def test_peer_learning_is_imported_as_candidate(tmp_path: Path):
    gene2 = GeneLearningEngine(tmp_path, "gene-node-2")
    gene3 = GeneLearningEngine(tmp_path, "gene-node-3")
    lesson = gene2.add_candidate(
        source_type="research",
        source_ref="paper-1",
        topic="memory",
        lesson="Validated lesson from Gene 002.",
        evidence={"source": "paper"},
        confidence=0.85,
    )
    gene2.validate(lesson.lesson_id, {"review": "passed"})
    packet = gene2.share_validated(lesson.lesson_id)

    imported = gene3.import_peer_packet(packet)
    assert imported.state == "candidate"
    assert imported.evidence["rule"] == "import_as_candidate_not_authority"
    assert gene3.status()["candidate"] == 1
    assert gene3.status()["validated"] == 0

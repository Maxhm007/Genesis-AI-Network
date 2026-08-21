from __future__ import annotations

import json

from genesis.autonomy_pipeline import PipelineStore
from genesis.evolution_learning import GenesisEvolutionLearningEngine, ResearchItem
from genesis.modules.task_queue import PersistentTaskQueue


class FakeProvider:
    name = "fake-learning-provider"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def reason(self, prompt: str) -> str:
        return json.dumps(self.payload)


def _item() -> ResearchItem:
    return ResearchItem(
        fingerprint="research-1",
        source="arxiv",
        title="Persistent memory improves autonomous agents",
        summary="A bounded retrieval memory can improve agent decisions across repeated tasks.",
        url="https://example.invalid/research-1",
        published_at="2026-08-21T00:00:00+00:00",
    )


def _engine(tmp_path, provider):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "memory_worker.py").write_text(
        '"""Agent memory worker."""\nSTATE = "ephemeral"\n',
        encoding="utf-8",
    )
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    pipeline = PipelineStore(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    return GenesisEvolutionLearningEngine(
        tmp_path,
        queue=queue,
        pipeline=pipeline,
        provider=provider,
        research_fetcher=lambda: ([_item()], []),
    ), queue, pipeline


def test_grounded_learning_enqueues_upgrade_and_logs_process(tmp_path):
    provider = FakeProvider(
        {
            "decision": "upgrade",
            "target_path": "genesis/memory_worker.py",
            "summary": "Make memory durable across repeated autonomous runs.",
            "acceptance": "A repeated run can retrieve a previously stored bounded memory record.",
            "learning_evidence": "bounded retrieval memory",
            "target_evidence": 'STATE = "ephemeral"',
            "confidence": 0.9,
        }
    )
    engine, queue, pipeline = _engine(tmp_path, provider)

    result = engine.run_once()

    assert result["status"] == "upgrade_enqueued"
    task = queue.get(result["task_id"])
    assert task is not None
    assert task.payload["task_type"] == "self_upgrade"
    assert task.payload["target_path"] == "genesis/memory_worker.py"
    assert pipeline.get(task.task_id).stage == "discovered"
    assert (tmp_path / "runtime" / "evolution" / "upgrade_process.json").is_file()
    assert (tmp_path / "runtime" / "evolution" / "upgrade_events.jsonl").is_file()


def test_ungrounded_upgrade_is_learned_but_not_enqueued(tmp_path):
    provider = FakeProvider(
        {
            "decision": "upgrade",
            "target_path": "genesis/memory_worker.py",
            "summary": "Change memory.",
            "acceptance": "Memory improves.",
            "learning_evidence": "not present in source",
            "target_evidence": 'STATE = "ephemeral"',
            "confidence": 0.95,
        }
    )
    engine, queue, _ = _engine(tmp_path, provider)

    result = engine.run_once()

    assert result["status"] == "learning_recorded_no_upgrade"
    assert queue.list(limit=10) == []


def test_active_upgrade_blocks_upgrade_flooding(tmp_path):
    provider = FakeProvider(
        {
            "decision": "upgrade",
            "target_path": "genesis/memory_worker.py",
            "summary": "Make memory durable across repeated autonomous runs.",
            "acceptance": "A repeated run can retrieve a previously stored bounded memory record.",
            "learning_evidence": "bounded retrieval memory",
            "target_evidence": 'STATE = "ephemeral"',
            "confidence": 0.9,
        }
    )
    engine, queue, _ = _engine(tmp_path, provider)
    first = engine.run_once()
    assert first["status"] == "upgrade_enqueued"

    second = engine.run_once()

    assert second["status"] == "active_upgrade_in_progress"
    assert second["active_task_ids"] == [first["task_id"]]
    assert len(queue.list(limit=10)) == 1

from __future__ import annotations

import json

from genesis.autonomy_pipeline import PipelineStore
from genesis.evolution_learning import GenesisEvolutionLearningEngine, ResearchItem
from genesis.modules.task_queue import PersistentTaskQueue


class TimeoutThenSkipProvider:
    name = "fake-learning-provider"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def reason(self, prompt: str) -> str:
        self.calls.append(prompt)
        if "First queued research" in prompt:
            raise TimeoutError("simulated slow research")
        return json.dumps({"decision": "skip", "summary": "No grounded upgrade for this item."})


class AlwaysTimeoutProvider:
    name = "fake-learning-provider"

    def reason(self, _prompt: str) -> str:
        raise TimeoutError("simulated slow research")


def _items() -> list[ResearchItem]:
    return [
        ResearchItem(
            fingerprint="research-first",
            source="arxiv",
            title="First queued research",
            summary="Agent memory and reasoning research that may require a slow assessment.",
            url="https://example.invalid/research-first",
            published_at="2026-08-21T02:00:00+00:00",
        ),
        ResearchItem(
            fingerprint="research-second",
            source="arxiv",
            title="Second queued research",
            summary="A separate agent memory result that can be assessed normally.",
            url="https://example.invalid/research-second",
            published_at="2026-08-21T01:00:00+00:00",
        ),
    ]


def _engine(tmp_path, provider, items):
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
        research_fetcher=lambda: (items, []),
    )


def test_timeout_moves_item_to_waiting_and_processes_next_item(tmp_path):
    provider = TimeoutThenSkipProvider()
    engine = _engine(tmp_path, provider, _items())

    result = engine.run_once()

    assert result["status"] == "learning_recorded_no_upgrade"
    assert len(provider.calls) == 2
    first = engine.store.research_record("research-first")
    second = engine.store.research_record("research-second")
    assert first is not None
    assert first["status"] == "waiting"
    assert first["retry_count"] == 1
    assert first["next_retry_at"]
    assert "TimeoutError" in first["last_error"]
    assert second is not None
    assert second["status"] == "evaluated"
    assert result["queue_transitions"][0]["status"] == "waiting"


def test_waiting_item_does_not_block_queue_when_no_other_item_is_ready(tmp_path):
    engine = _engine(tmp_path, AlwaysTimeoutProvider(), [_items()[0]])

    result = engine.run_once()

    assert result["status"] == "learning_waiting"
    assert result["learning_queue"]["counts"]["waiting"] == 1
    assert result["learning_queue"]["next_retry_at"]
    record = engine.store.research_record("research-first")
    assert record is not None
    assert record["status"] == "waiting"
    assert record["retry_count"] == 1


def test_retry_budget_quarantines_repeatedly_failing_research(tmp_path):
    engine = _engine(tmp_path, AlwaysTimeoutProvider(), [_items()[0]])
    engine.store.ingest([_items()[0]])
    claimed = engine.store.claim_next_ready()
    assert claimed is not None

    first = engine.store.defer_research(
        "research-first", "timeout-1", max_retries=3, base_delay_minutes=10
    )
    second = engine.store.defer_research(
        "research-first", "timeout-2", max_retries=3, base_delay_minutes=10
    )
    third = engine.store.defer_research(
        "research-first", "timeout-3", max_retries=3, base_delay_minutes=10
    )

    assert first["status"] == "waiting"
    assert second["status"] == "waiting"
    assert third["status"] == "quarantined"
    record = engine.store.research_record("research-first")
    assert record is not None
    assert record["status"] == "quarantined"
    assert record["retry_count"] == 3
    assert record["next_retry_at"] is None

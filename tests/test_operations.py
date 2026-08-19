from pathlib import Path

from genesis.operations import GenesisOperations


def scorecard(ai=37, samples=0, fresh=True):
    return {
        "ai_capability_score": {"score": ai, "max_score": 100},
        "efficiency_score": {"score": 0, "max_score": 100, "samples": samples},
        "immortality_research_progress_score": {"score": 50, "max_score": 100, "fresh_scan_24h": fresh},
    }


def test_detects_and_queues_measurable_operational_gaps(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issues = ops.detect(scorecard())
    titles = {item.title for item in issues}
    assert "AI capability below target" in titles
    assert "Efficiency telemetry insufficient" in titles
    result = ops.persist_and_queue(issues)
    assert len(result["created_tasks"]) == 2
    assert ops.report()["open"] == 2
    assert result["history_events"] >= 4


def test_resolves_issue_when_condition_disappears(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    ops.persist_and_queue(ops.detect(scorecard(ai=37, samples=0)))
    ops.persist_and_queue(ops.detect(scorecard(ai=75, samples=4)))
    report = ops.report()
    assert report["open"] == 0
    assert report["resolved"] == 2
    events = [row["event"] for row in ops.history()]
    assert events.count("resolved") == 2


def test_resolved_issue_remains_visible_in_later_collection_cycles(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    ops.persist_and_queue(ops.detect(scorecard(ai=37, samples=0)))
    ops.persist_and_queue(ops.detect(scorecard(ai=75, samples=4)))
    assert ops.report()["resolved"] == 2

    # A later healthy collection must not erase historical resolutions.
    ops.persist_and_queue(ops.detect(scorecard(ai=75, samples=4)))
    report = ops.report()
    assert report["open"] == 0
    assert report["resolved"] == 2
    assert {row["title"] for row in report["issues"] if row["status"] == "resolved"} == {
        "AI capability below target",
        "Efficiency telemetry insufficient",
    }


def test_issue_identity_survives_metric_improvement_while_still_open(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    first = ops.detect(scorecard(ai=37, samples=4))[0]
    second = ops.detect(scorecard(ai=42, samples=4))[0]
    assert first.issue_key == second.issue_key
    ops.persist_and_queue([first])
    ops.persist_and_queue([second])
    report = ops.report()
    assert report["open"] == 1
    assert report["resolved"] == 0
    assert report["issues"][0]["evidence"] == "AI Capability Score=42/100"


def test_history_rebuilds_from_cached_ledger_snapshot(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issue = ops.detect(scorecard(ai=37, samples=4))[0]
    ops.persist_and_queue([issue])
    expected = ops.history(issue.issue_key)
    assert expected
    ops.history_path.unlink()
    restored = GenesisOperations(tmp_path)
    assert restored.history(issue.issue_key) == expected


def test_stale_research_scan_becomes_persistent_task(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issues = ops.detect(scorecard(ai=80, samples=4, fresh=False))
    assert len(issues) == 1
    assert issues[0].title == "Immortality research scan stale"
    result = ops.persist_and_queue(issues)
    assert len(result["created_tasks"]) == 1


def test_issue_history_is_append_only_across_hourly_observations(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issue = ops.detect(scorecard(ai=37, samples=4))[0]
    ops.persist_and_queue([issue])
    first = ops.history(issue.issue_key)
    ops.persist_and_queue([issue])
    second = ops.history(issue.issue_key)
    assert len(second) > len(first)
    assert second[0]["event"] == "detected"
    assert any(row["event"] == "observed_open" for row in second)


def test_unresolved_issue_gets_new_work_generation_after_previous_task_ends(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issue = ops.detect(scorecard(ai=37, samples=4))[0]
    first = ops.persist_and_queue([issue])
    first_task_id = first["created_tasks"][0]
    ops.queue.transition(first_task_id, "assigned")
    ops.queue.transition(first_task_id, "running")
    ops.queue.transition(first_task_id, "review")
    ops.queue.transition(first_task_id, "complete")

    second = ops.persist_and_queue([issue])
    assert len(second["created_tasks"]) == 1
    assert second["created_tasks"][0] != first_task_id
    tasks = ops._tasks_for_issue(issue.issue_key)
    assert {task.payload.get("work_generation") for task in tasks} == {1, 2}
    events = [row for row in ops.history(issue.issue_key) if row["event"] == "repair_task_created"]
    assert [row["work_generation"] for row in events] == [1, 2]


def test_external_benchmark_blocker_stops_duplicate_ai_repair_generations(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issue = ops.detect(scorecard(ai=37, samples=4))[0]
    first = ops.persist_and_queue([issue])
    first_task_id = first["created_tasks"][0]
    ops.queue.transition(first_task_id, "assigned")
    ops.queue.transition(first_task_id, "running")
    ops.queue.transition(first_task_id, "review")
    ops.queue.transition(first_task_id, "complete")

    benchmark = ops.queue.create(
        "Measure Terminal-Bench with real provenance.",
        module_id="genesis.evaluation",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": "terminal_bench_2_1"},
        },
    )
    ops.queue.transition(benchmark.task_id, "assigned")
    ops.queue.transition(benchmark.task_id, "running")
    blocker_reason = (
        "External authority required for real benchmark execution: harbor_cli, GENESIS_BENCHMARK_AGENT. "
        "No score may change until validated evidence is staged."
    )
    ops.queue.pause(benchmark.task_id, blocker_reason)

    blocked = ops.persist_and_queue([issue])
    assert blocked["created_tasks"] == []
    row = ops.report()["issues"][0]
    assert row["status"] == "blocked"
    assert row["owner_action_required"] is True
    assert row["delegated_task_id"] == benchmark.task_id
    assert row["blocker_reason"] == blocker_reason
    assert row["work_generation"] == 1
    assert any(event["event"] == "delegated_external_blocker" for event in ops.history(issue.issue_key))


def test_ai_repair_eligibility_returns_when_delegated_blocker_clears(tmp_path: Path):
    ops = GenesisOperations(tmp_path)
    issue = ops.detect(scorecard(ai=37, samples=4))[0]
    first = ops.persist_and_queue([issue])
    first_task_id = first["created_tasks"][0]
    ops.queue.transition(first_task_id, "assigned")
    ops.queue.transition(first_task_id, "running")
    ops.queue.transition(first_task_id, "review")
    ops.queue.transition(first_task_id, "complete")

    benchmark = ops.queue.create(
        "Measure Terminal-Bench with real provenance.",
        module_id="genesis.evaluation",
        priority=92,
        payload={"task_type": "frontier_benchmark_measurement"},
    )
    ops.queue.transition(benchmark.task_id, "assigned")
    ops.queue.transition(benchmark.task_id, "running")
    ops.queue.pause(
        benchmark.task_id,
        "External authority required for real benchmark execution: harbor_cli. No score may change until validated evidence is staged.",
    )
    ops.persist_and_queue([issue])
    ops.queue.resume(benchmark.task_id)

    resumed = ops.persist_and_queue([issue])
    assert len(resumed["created_tasks"]) == 1
    row = ops.report()["issues"][0]
    assert row["status"] == "open"
    assert row["owner_action_required"] is False
    assert row["work_generation"] == 2
    assert any(event["event"] == "delegated_blocker_cleared" for event in ops.history(issue.issue_key))

from genesis.modules.task_queue import GenesisTask
from scripts.ai_team_dispatch import BENCHMARK_EVIDENCE_GUARD, build_team_context


def test_frontier_benchmark_context_marks_reference_score_as_not_measured():
    task = GenesisTask(
        task_id="task-test",
        objective="Measure Genesis on terminal_bench_2_1",
        module_id="genesis.evaluation",
        state="assigned",
        priority=92,
        payload={
            "task_type": "frontier_benchmark_measurement",
            "benchmark": {"benchmark_id": "terminal_bench_2_1", "reference_score": 91.9},
        },
        created_at="2026-08-17T00:00:00+00:00",
        updated_at="2026-08-17T00:00:00+00:00",
    )

    context = build_team_context(task)

    assert BENCHMARK_EVIDENCE_GUARD in context
    assert "reference_score is a comparison target only" in context
    assert "unmeasured_until_validated_result_exists" in context


def test_non_benchmark_context_does_not_add_benchmark_measurement_claims():
    task = GenesisTask(
        task_id="task-test",
        objective="Review network health",
        module_id="genesis.network",
        state="assigned",
        priority=50,
        payload={"task_type": "network_review"},
        created_at="2026-08-17T00:00:00+00:00",
        updated_at="2026-08-17T00:00:00+00:00",
    )

    context = build_team_context(task)

    assert "evidence_guard" not in context
    assert "measurement_status" not in context

from __future__ import annotations

import json
from pathlib import Path

from genesis.adaptive_team import PerformanceAdaptiveAITeam
from genesis.modules.task_queue import GenesisTask, PersistentTaskQueue
from genesis.providers import ProviderRegistry


BENCHMARK_EVIDENCE_GUARD = (
    "EVIDENCE GUARD: reference_score is a comparison target only. It is NOT a measured Genesis result. "
    "Do not claim that Genesis achieved, matched, passed, or was independently validated on a benchmark unless the context contains "
    "an actual measured result with status=validated plus provenance.source and provenance.measured_at. "
    "If those fields are absent, state that the benchmark remains unmeasured and recommend only a reproducible execution/ingestion step."
)


def build_team_context(task: GenesisTask) -> str:
    payload = dict(task.payload)
    context = {
        "owner_module": task.module_id,
        "priority": task.priority,
        "payload": payload,
    }
    if payload.get("task_type") == "frontier_benchmark_measurement":
        context["evidence_guard"] = BENCHMARK_EVIDENCE_GUARD
        context["measurement_status"] = "unmeasured_until_validated_result_exists"
    return json.dumps(context, sort_keys=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    route_path = runtime / "task_route.json"
    report = {"status": "not_requested", "task_id": None, "outputs": []}

    if route_path.is_file():
        route = json.loads(route_path.read_text(encoding="utf-8"))
        decision = route.get("decision") or {}
        task_id = str(decision.get("task_id", ""))
        use_ai_team = bool(decision.get("use_ai_team", False))
        report["task_id"] = task_id or None
        if use_ai_team and task_id:
            queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
            task = queue.get(task_id)
            if task is not None:
                team = PerformanceAdaptiveAITeam(
                    ProviderRegistry(),
                    preferences_path=runtime / "learning_preferences.json",
                )
                context = build_team_context(task)
                plan = team.plan_task(task.objective, context=context)
                outputs = team.run_task(task.objective, context=context)
                report = {
                    "status": "completed",
                    "task_id": task.task_id,
                    "objective": task.objective,
                    "owner_module": task.module_id,
                    "outputs": outputs,
                    "learning_domain": team._current_domain,
                    "selected_roles": list(plan.role_names),
                    "composition_reason": plan.reason,
                    "rule": (
                        "AI Team provides bounded specialist analysis. The owning module remains responsible for execution and normal "
                        "Security/validation gates still apply. Historical agent and provider preferences are based only on repeated "
                        "measured operational outcomes. Learning cannot remove required planner, domain-owner, reviewer, or validator "
                        "roles and never converts candidate knowledge into validated fact. Benchmark reference scores are never "
                        "treated as measured Genesis results."
                    ),
                }

    (runtime / "ai_team_dispatch.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))

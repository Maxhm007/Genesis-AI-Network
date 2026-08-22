from __future__ import annotations

import argparse
import json
import signal
import subprocess
import time
from pathlib import Path

from genesis.agentic import AgenticPulseController
from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.goal_directed_pipeline import GoalDirectedPipelineCoordinator
from genesis.goal_orchestrator import GoalOrchestrator
from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.proactive import ProactiveDevelopmentLoop
from genesis.self_learning import SelfLearningEngine
from genesis.work_rule import GeneWorkRule, WorkDecision


ROOT = Path(__file__).resolve().parents[1]
STOP = False
PULSE_DISCOVERY_SOURCE_BYTES = 5_000
PULSE_DISCOVERY_TEST_BYTES = 2_000
BENCHMARK_RUNNER_TASK_TYPE = "benchmark_runner_integration"
BENCHMARK_RUNNER_EXECUTABLE_STATES = {"new", "assigned", "blocked", "failed", "review"}
BENCHMARK_RUNNER_STATE_PRIORITY = {
    "review": 0,
    "assigned": 1,
    "blocked": 1,
    "failed": 1,
    "new": 1,
}
PIPELINE_COMPLETION_PRIORITY_STAGES = {"review_ready", "validation_ready", "promoted"}


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def _handoff_path(logical_id: str) -> Path:
    path = ROOT / "runtime" / "grce" / logical_id / "candidate_handoff.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_handoff(logical_id: str) -> dict:
    path = _handoff_path(logical_id)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_handoff(logical_id: str, *, task_id: str, branch: str, candidate_sha: str) -> dict:
    payload = {
        "task_id": task_id,
        "branch": branch,
        "candidate_sha": candidate_sha,
        "state": "waiting_validation",
    }
    _handoff_path(logical_id).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _candidate_promoted(candidate_sha: str) -> bool:
    if not candidate_sha:
        return False
    subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT, check=False, capture_output=True, text=True)
    direct = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, "origin/main"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if direct.returncode == 0:
        return True
    cherry = subprocess.run(
        ["git", "cherry", "origin/main", candidate_sha],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def _pipeline_decision(pipeline: dict) -> dict:
    record = dict(pipeline.get("record") or {})
    return {
        "mode": "autonomy_pipeline",
        "task_id": record.get("task_id") or pipeline.get("discovery", {}).get("task_id"),
        "stage": record.get("stage"),
        "worker_action": pipeline.get("action"),
    }


def _legacy_task_coding_ready(engineering: AutonomousEngineeringLoop, task) -> bool:
    if task is None:
        return False
    return bool(engineering._context_paths_for_task(task))


def _next_benchmark_runner_task(queue):
    """Return one executable benchmark-runner integration task, if any.

    A runner already in review owns the single candidate handoff for this Gene and
    therefore finishes before newer runner coding work. Blocked runner tasks remain
    executable so a corrected implementation/context can resume them on a later Pulse.
    """
    candidates = []
    for task in queue.list(limit=5000):
        payload = dict(task.payload or {})
        if payload.get("task_type") != BENCHMARK_RUNNER_TASK_TYPE:
            continue
        if task.state not in BENCHMARK_RUNNER_EXECUTABLE_STATES:
            continue
        if task.state == "failed" and not queue.retryable(task):
            continue
        candidates.append(task)
    candidates.sort(
        key=lambda task: (
            BENCHMARK_RUNNER_STATE_PRIORITY.get(task.state, 99),
            -task.priority,
            task.created_at,
            task.task_id,
        )
    )
    return candidates[0] if candidates else None


def _pipeline_completion_has_priority(pipeline: GoalDirectedPipelineCoordinator) -> bool:
    """Poll durable candidate completion before starting fresh benchmark coding."""
    return any(
        str(getattr(record, "stage", "")) in PIPELINE_COMPLETION_PRIORITY_STAGES
        for record in pipeline.store.list_active()
    )


def _completion_poll_blocks_benchmark_runner(pipeline_result: dict) -> bool:
    """A no-change validation wait must not consume every future benchmark Pulse."""
    if not pipeline_result.get("handled"):
        return False
    return str(pipeline_result.get("action") or "") != "pipeline_wait_validation"


def _finalize_agentic(
    controller: AgenticPulseController,
    planned_step,
    goals: GoalOrchestrator,
    orchestration: dict,
    result: dict,
) -> dict:
    goal_observation = goals.observe(result)
    agentic = controller.observe(result)
    agentic["planned_step"] = dict(planned_step.__dict__)
    result["agentic"] = agentic
    result["goal_orchestration"] = {
        "before": orchestration,
        "after": goal_observation,
    }
    return result


def _run_legacy_task(logical_id: str, engineering: AutonomousEngineeringLoop, rule: GeneWorkRule, decision) -> dict:
    result: dict = {"decision": decision.__dict__}
    task = engineering.queue.get(decision.task_id) if decision.task_id else None
    if task is None:
        rule.clear_focus()
        result["action"] = "focus_missing_reassess"
        return result
    if task.state == "review":
        handoff = _load_handoff(logical_id)
        candidate_sha = str(handoff.get("candidate_sha") or "")
        if handoff.get("task_id") == task.task_id and _candidate_promoted(candidate_sha):
            engineering.queue.transition(task.task_id, "complete", module_id=task.module_id)
            rule.clear_focus()
            handoff["state"] = "promotion_confirmed"
            _handoff_path(logical_id).write_text(
                json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            result["action"] = "promotion_observed_reassess"
            result["promotion"] = handoff
            result["next_decision"] = rule.decide().__dict__
            return result
        result["action"] = "hold_focus_while_validation_finishes"
        result["candidate_handoff"] = handoff
        return result

    runtime = ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    result["action"] = "attempt_focused_issue"
    old_revision_budget = engineering.MAX_CANDIDATE_REVISIONS
    engineering.MAX_CANDIDATE_REVISIONS = 0
    try:
        attempt = engineering._attempt_task(task, runtime)
    finally:
        engineering.MAX_CANDIDATE_REVISIONS = old_revision_budget
    result["attempt"] = attempt
    candidate = dict(attempt.get("candidate") or {})
    security = dict(attempt.get("candidate_security") or {})
    if (
        attempt.get("coding_status") == "candidate_created"
        and candidate.get("committed")
        and candidate.get("commit_sha")
        and candidate.get("branch")
        and security.get("status") == "pass"
    ):
        result["candidate_handoff"] = _write_handoff(
            logical_id,
            task_id=task.task_id,
            branch=str(candidate["branch"]),
            candidate_sha=str(candidate["commit_sha"]),
        )
    return result


def run_step(logical_id: str) -> dict:
    # Keep the Pulse-specific discovery prompt small enough for the local CPU
    # specialist. Other workflows retain the canonical larger discovery limits.
    GenesisIssueDiscoveryEngine.MAX_SOURCE_BYTES = PULSE_DISCOVERY_SOURCE_BYTES
    GenesisIssueDiscoveryEngine.MAX_TEST_BYTES = PULSE_DISCOVERY_TEST_BYTES

    engineering = AutonomousEngineeringLoop(ROOT)
    pipeline = GoalDirectedPipelineCoordinator(ROOT, engineering)
    goals = GoalOrchestrator(ROOT, logical_id)
    orchestration = goals.sync(pipeline)
    selected = dict(orchestration.get("selected") or {})
    selected_goal = dict(selected.get("goal") or {})
    preferred_task_id = selected_goal.get("task_id")

    agentic = AgenticPulseController(ROOT, logical_id)
    planned_step = agentic.plan(pipeline)

    # Frontier benchmark parents pause while a bounded runner-integration coding
    # task is outstanding. Poll candidate completion first. A real review,
    # promotion, or learning transition consumes this Pulse; a validation wait that
    # made no state change does not permanently starve benchmark execution.
    benchmark_runner = _next_benchmark_runner_task(engineering.queue)
    if benchmark_runner is not None:
        completion_poll = None
        if _pipeline_completion_has_priority(pipeline):
            completion_poll = pipeline.run_once(preferred_task_id=None)
            if _completion_poll_blocks_benchmark_runner(completion_poll):
                return _finalize_agentic(
                    agentic,
                    planned_step,
                    goals,
                    orchestration,
                    {
                        "decision": _pipeline_decision(completion_poll),
                        "action": completion_poll.get("action", "pipeline_unknown"),
                        "pipeline": completion_poll,
                    },
                )

        rule = GeneWorkRule(ROOT, logical_id, engineering.queue)
        decision = WorkDecision(
            gene=rule.identity.display_name,
            logical_id=logical_id,
            mode="solve_issue",
            task_id=benchmark_runner.task_id,
            objective=benchmark_runner.objective,
            reason="frontier_benchmark_runner_priority",
        )
        result = _run_legacy_task(logical_id, engineering, rule, decision)
        result["benchmark_runner_priority"] = {
            "task_id": benchmark_runner.task_id,
            "benchmark_id": str(benchmark_runner.payload.get("benchmark_id") or ""),
            "state": benchmark_runner.state,
            "priority": benchmark_runner.priority,
        }
        if completion_poll is not None:
            result["pipeline_completion_poll"] = {
                "action": completion_poll.get("action"),
                "record": completion_poll.get("record"),
            }
        return _finalize_agentic(agentic, planned_step, goals, orchestration, result)

    pipeline_result = pipeline.run_once(preferred_task_id=str(preferred_task_id) if preferred_task_id else None)

    if pipeline_result.get("handled"):
        return _finalize_agentic(
            agentic,
            planned_step,
            goals,
            orchestration,
            {
                "decision": _pipeline_decision(pipeline_result),
                "action": pipeline_result.get("action", "pipeline_unknown"),
                "pipeline": pipeline_result,
            },
        )

    # Keep legacy code tasks functional, but never let a contextless capability,
    # benchmark, or administrative task hijack the coding/repair Pulse.
    rule = GeneWorkRule(ROOT, logical_id, engineering.queue)
    decision = rule.decide()
    legacy_skipped = None
    if decision.mode == "solve_issue" and decision.task_id:
        task = engineering.queue.get(decision.task_id)
        if not pipeline.is_pipeline_task(task):
            if _legacy_task_coding_ready(engineering, task):
                result = _run_legacy_task(logical_id, engineering, rule, decision)
                result["pipeline_discovery"] = pipeline_result.get("discovery")
                return _finalize_agentic(agentic, planned_step, goals, orchestration, result)
            legacy_skipped = {
                "task_id": task.task_id if task else decision.task_id,
                "module_id": task.module_id if task else None,
                "reason": "no_bounded_code_context_for_gene_pulse",
            }
            rule.clear_focus()
        else:
            rule.clear_focus()

    # No executable repair work remains. Discovery already completed one full
    # source cycle and found no confirmed issue, so use broader learning work and
    # checkpoint rather than repeatedly attempting an unrelated legacy task.
    result: dict = {
        "decision": {
            "mode": "learn_discover",
            "task_id": None,
            "reason": "pipeline_no_executable_issue",
        },
        "action": "learn_discover_reassess",
        "discovery": pipeline_result.get("discovery"),
    }
    if legacy_skipped:
        result["legacy_skipped"] = legacy_skipped
    result["learning"] = SelfLearningEngine(ROOT).run_once()
    proactive = ProactiveDevelopmentLoop(ROOT)
    result["score_work"] = proactive.ensure_score_work()
    result["velocity_work"] = proactive.ensure_velocity_work()
    result["capability_scan"] = proactive.inspect()[:5]

    next_decision = rule.decide().__dict__
    next_task_id = next_decision.get("task_id")
    if next_decision.get("mode") == "solve_issue" and next_task_id:
        next_task = engineering.queue.get(str(next_task_id))
        if next_task and not pipeline.is_pipeline_task(next_task) and not _legacy_task_coding_ready(engineering, next_task):
            next_decision = {
                "mode": "idle",
                "task_id": None,
                "reason": "non_coding_legacy_task_not_executable_by_gene_pulse",
            }
    result["next_decision"] = next_decision
    return _finalize_agentic(agentic, planned_step, goals, orchestration, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Gene continuously, one bounded queue transition at a time.")
    parser.add_argument("--gene", default="gene-node-1", help="Internal Gene logical id")
    parser.add_argument("--once", action="store_true", help="Run one decision step and exit")
    parser.add_argument("--idle-pause", type=float, default=5.0, help="Small anti-spin pause; not a work schedule")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not STOP:
        result = run_step(args.gene)
        print(json.dumps(result, sort_keys=True), flush=True)
        if args.once:
            break
        time.sleep(max(0.1, args.idle_pause))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

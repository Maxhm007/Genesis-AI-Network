from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.proactive import ProactiveDevelopmentLoop
from genesis.self_learning import SelfLearningEngine
from genesis.work_rule import GeneWorkRule


ROOT = Path(__file__).resolve().parents[1]
STOP = False


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def run_step(logical_id: str) -> dict:
    engineering = AutonomousEngineeringLoop(ROOT)
    rule = GeneWorkRule(ROOT, logical_id, engineering.queue)
    decision = rule.decide()
    result: dict = {"decision": decision.__dict__}

    if decision.mode == "solve_issue" and decision.task_id:
        task = engineering.queue.get(decision.task_id)
        if task is None:
            rule.clear_focus()
            result["action"] = "focus_missing_reassess"
            return result
        if task.state == "review":
            result["action"] = "hold_focus_while_validation_finishes"
            return result
        runtime = ROOT / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        result["action"] = "attempt_focused_issue"
        result["attempt"] = engineering._attempt_task(task, runtime)
        return result

    # No issue exists. Learn from current evidence, inspect capability gaps and
    # create real work when a measurable gap is found. Network/web discovery is
    # an allowed idle action when the deployed runtime has an authorized network
    # research provider; the core loop does not fabricate web evidence.
    result["action"] = "learn_discover_reassess"
    result["learning"] = SelfLearningEngine(ROOT).run_once()
    proactive = ProactiveDevelopmentLoop(ROOT)
    result["score_work"] = proactive.ensure_score_work()
    result["velocity_work"] = proactive.ensure_velocity_work()
    result["capability_scan"] = proactive.inspect()[:5]
    result["next_decision"] = rule.decide().__dict__
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Gene continuously, one issue at a time.")
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
        # This pause only prevents a busy CPU loop. Work authority comes from
        # persistent issue state, never from a cron/hourly/minute schedule.
        time.sleep(max(0.1, args.idle_pause))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

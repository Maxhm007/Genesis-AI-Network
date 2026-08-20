from __future__ import annotations

import argparse
import json
import signal
import subprocess
import time
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.proactive import ProactiveDevelopmentLoop
from genesis.self_learning import SelfLearningEngine
from genesis.work_rule import GeneWorkRule


ROOT = Path(__file__).resolve().parents[1]
STOP = False


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
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


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
        attempt = engineering._attempt_task(task, runtime)
        result["attempt"] = attempt
        candidate = dict(attempt.get("candidate") or {})
        candidate_security = dict(attempt.get("candidate_security") or {})
        if (
            attempt.get("coding_status") == "candidate_created"
            and candidate.get("committed")
            and candidate.get("commit_sha")
            and candidate.get("branch")
            and candidate_security.get("status") == "pass"
        ):
            result["candidate_handoff"] = _write_handoff(
                logical_id,
                task_id=task.task_id,
                branch=str(candidate["branch"]),
                candidate_sha=str(candidate["commit_sha"]),
            )
        return result

    # No unresolved issue exists. Run evidence-driven code discovery first. A
    # confirmed finding becomes persistent queue work, so the next pulse keeps
    # focus on it instead of returning to generic learning/capability scanning.
    provider = engineering.coding._provider()
    discovery = GenesisIssueDiscoveryEngine(ROOT).discover_and_enqueue(engineering.queue, provider)
    result["action"] = "learn_discover_reassess"
    result["discovery"] = discovery
    result["next_decision"] = rule.decide().__dict__
    if result["next_decision"].get("mode") == "solve_issue":
        return result

    # Discovery found no confirmed issue. Continue the broader learning and
    # capability-gap path, then reassess once more before checkpointing.
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

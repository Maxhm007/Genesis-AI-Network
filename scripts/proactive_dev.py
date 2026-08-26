from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.file_self_review_policy import QuorumFileSelfReviewLoop
from genesis.proactive import DevelopmentPlan, ProactiveDevelopmentLoop
from genesis.self_improvement_issue_router import (
    create_planned_self_improvement_task,
    route_self_improvement,
)
from genesis.velocity import AdaptiveVelocityController


def _durable_issue_handoff(review_loop: QuorumFileSelfReviewLoop, proposal: dict, issue_number: int, source_task_id: str) -> None:
    """Release file-review focus once the improvement is durably owned by GitHub.

    The Issue/task pair now owns implementation and retries, so file review may
    continue scanning other files without creating a duplicate candidate lane.
    """
    meta = dict(proposal.get("file_self_review", {}) or {})
    if not meta:
        return
    state = review_loop._load()
    current = state.get("current") or {}
    if str(current.get("path") or "") != str(meta.get("path") or ""):
        return
    cycle_id = str(meta.get("cycle_id") or current.get("cycle_id") or "")
    review_loop.proof.record(
        cycle_id=cycle_id,
        stage="github_issue_handoff",
        actor="genesis.file_self_review",
        outcome="success",
        details={
            "path": current.get("path"),
            "github_issue_number": issue_number,
            "source_task_id": source_task_id,
            "execution_lane": "github_issue",
        },
    )
    review_loop._advance(
        state,
        {
            "status": "queued_to_github_issue",
            "reviewed_at": review_loop._now(),
            "improvement": current.get("improvement"),
            "github_issue_number": issue_number,
            "source_task_id": source_task_id,
            "cycle_id": cycle_id,
        },
    )


def _issue_for_source(routing: dict, source_task_id: str) -> int:
    for section in ("routed", "already_routed"):
        for row in routing.get(section, []) or []:
            if str(row.get("source_task_id") or "") == source_task_id:
                return int(row.get("github_issue_number") or 0)
    return 0


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = ProactiveDevelopmentLoop(root)
    review_loop = QuorumFileSelfReviewLoop(root, loop.providers)
    score = loop.ai_score_report()
    proof_before = AutonomyProofLedger(root).report()
    velocity_policy = AdaptiveVelocityController(root).policy()

    # Genesis still detects and designs bounded self-improvements. Execution is
    # no longer allowed here: every improvement is persisted and handed to a
    # GitHub Issue before any future coding attempt may start.
    development_source = "file_by_file_self_review"
    review_plan = review_loop.plan_next()
    if review_plan is not None:
        plan = DevelopmentPlan(
            title=str(review_plan["title"]),
            rationale=str(review_plan["rationale"]),
            proposal=dict(review_plan["proposal"]),
        )
    else:
        development_source = "legacy_task_or_capability_fallback"
        plan = loop.plan_next()

    if plan is None:
        print(json.dumps({
            "status": "no_self_improvement_issue_this_cycle",
            "development_source": development_source,
            "ai_score": score,
            "update_pressure": score["urgency"],
            "autonomy_proof": proof_before,
            "adaptive_velocity": velocity_policy,
            "inspection": loop.inspect(),
            "file_self_review": review_loop.status(),
        }, indent=2))
        return

    source_task, created = create_planned_self_improvement_task(
        root,
        title=plan.title,
        rationale=plan.rationale,
        proposal=plan.proposal,
        development_source=development_source,
    )
    if source_task is None:
        print(json.dumps({
            "status": "self_improvement_plan_not_routable",
            "development_source": development_source,
            "plan": asdict(plan),
        }, indent=2, sort_keys=True))
        raise SystemExit(1)

    routing = route_self_improvement(root)
    issue_number = _issue_for_source(routing, source_task.task_id)
    if issue_number <= 0:
        print(json.dumps({
            "status": "self_improvement_issue_handoff_blocked",
            "development_source": development_source,
            "source_task_id": source_task.task_id,
            "source_task_created": created,
            "routing": routing,
            "plan": asdict(plan),
        }, indent=2, sort_keys=True))
        raise SystemExit(1)

    _durable_issue_handoff(review_loop, plan.proposal, issue_number, source_task.task_id)
    payload = {
        "status": "self_improvement_issue_queued",
        "development_source": development_source,
        "source_task_id": source_task.task_id,
        "source_task_created": created,
        "github_issue_number": issue_number,
        "execution_lane": "github_issue",
        "direct_candidate_created": False,
        "ai_score": score,
        "update_pressure": score["urgency"],
        "autonomy_proof_before_cycle": proof_before,
        "autonomy_proof_after_cycle": AutonomyProofLedger(root).report(),
        "adaptive_velocity": AdaptiveVelocityController(root).policy(),
        "file_self_review": review_loop.status(),
        "plan": asdict(plan),
        "routing": routing,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

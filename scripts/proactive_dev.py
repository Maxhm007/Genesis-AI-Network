from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.file_self_review_policy import QuorumFileSelfReviewLoop
from genesis.proactive import DevelopmentPlan, ProactiveDevelopmentLoop
from genesis.self_improvement_issue_router import create_planned_self_improvement_task
from genesis.velocity import AdaptiveVelocityController


def _durable_source_handoff(review_loop: QuorumFileSelfReviewLoop, proposal: dict, source_task_id: str) -> None:
    """Release file-review focus after a non-executable source task is persisted.

    The next token-enabled task-router pass must convert this source task to a
    GitHub Issue before assignment. No direct candidate is created here.
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
        stage="github_issue_source_queued",
        actor="genesis.file_self_review",
        outcome="success",
        details={
            "path": current.get("path"),
            "source_task_id": source_task_id,
            "required_execution_lane": "github_issue",
        },
    )
    review_loop._advance(
        state,
        {
            "status": "queued_for_github_issue",
            "reviewed_at": review_loop._now(),
            "improvement": current.get("improvement"),
            "source_task_id": source_task_id,
            "cycle_id": cycle_id,
            "direct_candidate_created": False,
        },
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = ProactiveDevelopmentLoop(root)
    review_loop = QuorumFileSelfReviewLoop(root, loop.providers)
    score = loop.ai_score_report()
    proof_before = AutonomyProofLedger(root).report()
    velocity_policy = AdaptiveVelocityController(root).policy()

    # Genesis may inspect and design its own improvements here, but this script
    # is detection-only. It persists a source finding; the next task-router pass
    # creates/reuses a GitHub Issue and pauses that source before any assignment.
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
            "status": "no_self_improvement_source_this_cycle",
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

    _durable_source_handoff(review_loop, plan.proposal, source_task.task_id)
    payload = {
        "status": "self_improvement_source_queued_for_github_issue",
        "development_source": development_source,
        "source_task_id": source_task.task_id,
        "source_task_created": created,
        "required_execution_lane": "github_issue",
        "direct_candidate_created": False,
        "ai_score": score,
        "update_pressure": score["urgency"],
        "autonomy_proof_before_cycle": proof_before,
        "autonomy_proof_after_cycle": AutonomyProofLedger(root).report(),
        "adaptive_velocity": AdaptiveVelocityController(root).policy(),
        "file_self_review": review_loop.status(),
        "plan": asdict(plan),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.file_self_review import FileSelfReviewLoop
from genesis.proactive import DevelopmentPlan, ProactiveDevelopmentLoop
from genesis.velocity import AdaptiveVelocityController


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = ProactiveDevelopmentLoop(root)
    review_loop = FileSelfReviewLoop(root, loop.providers)
    score = loop.ai_score_report()
    proof_before = AutonomyProofLedger(root).report()
    velocity_policy = AdaptiveVelocityController(root).policy()

    # The workflow reaches this script only after the main autonomous engineering
    # lane failed to produce a candidate. At that point Genesis's intrinsic
    # behavior is to review exactly one source file before falling back to the
    # older bootstrap/module catalog planner.
    plan = None
    result = None
    development_source = "file_by_file_self_review"
    review_plan = review_loop.plan_next()
    if review_plan is not None:
        plan = DevelopmentPlan(
            title=str(review_plan["title"]),
            rationale=str(review_plan["rationale"]),
            proposal=dict(review_plan["proposal"]),
        )
        result = loop.executor.execute(plan.proposal)
        review_loop.observe_execution(plan.proposal, result)
    else:
        development_source = "legacy_task_or_capability_fallback"
        plan, result = loop.develop_once()

    if plan is None or result is None:
        print(json.dumps({
            "status": "no_candidate_this_cycle",
            "development_source": development_source,
            "ai_score": score,
            "update_pressure": score["urgency"],
            "autonomy_proof": proof_before,
            "adaptive_velocity": velocity_policy,
            "inspection": loop.inspect(),
            "file_self_review": review_loop.status(),
        }, indent=2))
        return

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "development_source": development_source,
        "ai_score": score,
        "update_pressure": score["urgency"],
        "autonomy_proof_before_cycle": proof_before,
        "autonomy_proof_after_cycle": AutonomyProofLedger(root).report(),
        "adaptive_velocity": AdaptiveVelocityController(root).policy(),
        "file_self_review": review_loop.status(),
        "plan": asdict(plan),
        "result": asdict(result),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if not (result.tests_passed and result.committed and result.commit_sha):
        raise SystemExit(1)

    subprocess.run(["git", "push", "--set-upstream", "origin", result.branch], cwd=root, check=True)


if __name__ == "__main__":
    main()

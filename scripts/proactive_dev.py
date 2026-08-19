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
    score = loop.ai_score_report()
    proof_before = AutonomyProofLedger(root).report()
    velocity_policy = AdaptiveVelocityController(root).policy()
    plan, result = loop.develop_once()
    review_loop = FileSelfReviewLoop(root, loop.providers)
    development_source = "task_or_capability_driven"

    # Intrinsic self-development fallback: when normal issue/task/capability work
    # did not create a candidate, Genesis reviews exactly one of its own source
    # files. The review cursor and lab survive hosted-run turnover under
    # runtime/task_reviews, which is already part of the persistent runtime
    # cache. A failed file stays focused and is retried by another method later.
    if plan is None or result is None:
        review_plan = review_loop.plan_next()
        if review_plan is not None:
            development_source = "file_by_file_self_review"
            plan = DevelopmentPlan(
                title=str(review_plan["title"]),
                rationale=str(review_plan["rationale"]),
                proposal=dict(review_plan["proposal"]),
            )
            result = loop.executor.execute(plan.proposal)
            review_loop.observe_execution(plan.proposal, result)

    if plan is None or result is None:
        print(json.dumps({
            "status": "no_candidate_this_cycle",
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

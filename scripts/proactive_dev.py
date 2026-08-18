from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.proactive import ProactiveDevelopmentLoop
from genesis.velocity import AdaptiveVelocityController


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = ProactiveDevelopmentLoop(root)
    score = loop.ai_score_report()
    proof_before = AutonomyProofLedger(root).report()
    velocity_policy = AdaptiveVelocityController(root).policy()
    plan, result = loop.develop_once()

    if plan is None or result is None:
        print(json.dumps({
            "status": "no_bounded_gap_detected",
            "ai_score": score,
            "update_pressure": score["urgency"],
            "autonomy_proof": proof_before,
            "adaptive_velocity": velocity_policy,
            "inspection": loop.inspect(),
        }, indent=2))
        return

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "ai_score": score,
        "update_pressure": score["urgency"],
        "autonomy_proof_before_cycle": proof_before,
        "autonomy_proof_after_cycle": AutonomyProofLedger(root).report(),
        "adaptive_velocity": AdaptiveVelocityController(root).policy(),
        "plan": asdict(plan),
        "result": asdict(result),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if not (result.tests_passed and result.committed and result.commit_sha):
        raise SystemExit(1)

    subprocess.run(["git", "push", "--set-upstream", "origin", result.branch], cwd=root, check=True)


if __name__ == "__main__":
    main()

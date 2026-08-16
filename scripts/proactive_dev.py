from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.proactive import ProactiveDevelopmentLoop


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = ProactiveDevelopmentLoop(root)
    score = loop.ai_score_report()
    plan, result = loop.develop_once()

    if plan is None or result is None:
        print(json.dumps({
            "status": "no_bounded_gap_detected",
            "ai_score": score,
            "update_pressure": score["urgency"],
            "inspection": loop.inspect(),
        }, indent=2))
        return

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "ai_score": score,
        "update_pressure": score["urgency"],
        "plan": asdict(plan),
        "result": asdict(result),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if not (result.tests_passed and result.committed and result.commit_sha):
        raise SystemExit(1)

    subprocess.run(
        ["git", "push", "--set-upstream", "origin", result.branch],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()

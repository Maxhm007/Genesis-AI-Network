from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.proactive import ProactiveDevelopmentLoop


def main() -> None:
    root = Path(__file__).resolve().parents[1]

    # Do not create competing autonomous candidates. One candidate must finish
    # validation before Genesis starts another development cycle.
    existing = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--json", "headRefName", "--limit", "50"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ},
    )
    if existing.returncode == 0:
        try:
            prs = json.loads(existing.stdout or "[]")
        except json.JSONDecodeError:
            prs = []
        if any(str(item.get("headRefName", "")).startswith("genesis/candidate-") for item in prs):
            print(json.dumps({"status": "waiting_for_existing_candidate"}, indent=2))
            return

    loop = ProactiveDevelopmentLoop(root)
    plan, result = loop.develop_once()
    if plan is None or result is None:
        print(json.dumps({"status": "no_bounded_gap_detected", "inspection": loop.inspect()}, indent=2))
        return

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
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
    subprocess.run(
        [
            "gh", "pr", "create",
            "--base", "main",
            "--head", result.branch,
            "--title", f"Genesis proactive development: {plan.title}",
            "--body",
            (
                "Genesis created this improvement from its proactive self-inspection.\n\n"
                f"Rationale: {plan.rationale}\n\n"
                "The candidate passed the full local test suite before commit and must "
                "still pass the independent validator quorum before promotion."
            ),
        ],
        cwd=root,
        check=True,
        env={**os.environ},
    )


if __name__ == "__main__":
    main()

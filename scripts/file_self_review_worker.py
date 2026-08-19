from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.file_self_review import FileSelfReviewLoop
from genesis.selfdev import SelfDevelopmentExecutor


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = FileSelfReviewLoop(root)
    plan = loop.plan_next()

    if plan is None:
        print(json.dumps({"status": "review_recorded_or_retry_pending", "file_self_review": loop.status()}, indent=2, sort_keys=True))
        return

    executor = SelfDevelopmentExecutor(root)
    result = executor.execute(dict(plan["proposal"]))
    loop.observe_execution(dict(plan["proposal"]), result)

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "plan": {"title": plan["title"], "rationale": plan["rationale"]},
        "result": asdict(result),
        "file_self_review": loop.status(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if result.tests_passed and result.committed and result.commit_sha:
        subprocess.run(["git", "push", "--set-upstream", "origin", result.branch], cwd=root, check=True)
        return

    # A failed lab candidate must not leave the workflow on an empty candidate
    # branch. Keep the persistent review state, return to main, and let the next
    # cycle retry the same file with a different method.
    subprocess.run(["git", "checkout", "main"], cwd=root, check=False, capture_output=True, text=True)


if __name__ == "__main__":
    main()

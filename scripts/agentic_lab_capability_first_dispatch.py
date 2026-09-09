from __future__ import annotations

import json
import os

import agentic_lab_recovery_dispatch as agentic
from capability_issue_priority_dispatch import quarantined_for_current_generation
from requeue_exhausted_issues import engine_generation


def prioritized_agentic_issues(repository: str, token: str) -> list[dict]:
    """Return eligible capability work before ordinary Agentic Lab work.

    Capability Issues quarantined for the current repair-engine generation are
    omitted entirely. This keeps Agentic Lab aligned with the capability-priority
    scheduler and prevents the same exhausted capability Issue from being
    recycled by a different workflow.
    """
    current_generation = engine_generation()
    capability: list[dict] = []
    ordinary: list[dict] = []
    quarantined: list[int] = []

    for issue in agentic.open_agentic_issues(repository, token):
        body = str(issue.get("body") or "")
        if agentic.CAPABILITY_WORK_PREFIX not in body:
            ordinary.append(issue)
            continue

        number = int(issue.get("number") or 0)
        comments = agentic.issue_comments(repository, token, number)
        if quarantined_for_current_generation(comments, current_generation):
            quarantined.append(number)
            continue
        capability.append(issue)

    print(
        json.dumps(
            {
                "selector": "capability_first",
                "repair_engine_generation": current_generation,
                "eligible_capability_issues": [int(row.get("number") or 0) for row in capability],
                "quarantined_capability_issues": quarantined,
                "ordinary_agentic_issues": len(ordinary),
            },
            sort_keys=True,
        )
    )
    return capability + ordinary


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    original_selector = agentic.open_agentic_issues

    def _selector(repo: str, tok: str) -> list[dict]:
        # Use the original selector here to avoid recursive monkey-patching.
        current_generation = engine_generation()
        capability: list[dict] = []
        ordinary: list[dict] = []
        quarantined: list[int] = []
        for issue in original_selector(repo, tok):
            body = str(issue.get("body") or "")
            if agentic.CAPABILITY_WORK_PREFIX not in body:
                ordinary.append(issue)
                continue
            number = int(issue.get("number") or 0)
            comments = agentic.issue_comments(repo, tok, number)
            if quarantined_for_current_generation(comments, current_generation):
                quarantined.append(number)
                continue
            capability.append(issue)
        print(json.dumps({
            "selector": "capability_first",
            "repair_engine_generation": current_generation,
            "eligible_capability_issues": [int(row.get("number") or 0) for row in capability],
            "quarantined_capability_issues": quarantined,
            "ordinary_agentic_issues": len(ordinary),
        }, sort_keys=True))
        return capability + ordinary

    agentic.open_agentic_issues = _selector
    agentic.reserve_and_dispatch(repository, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

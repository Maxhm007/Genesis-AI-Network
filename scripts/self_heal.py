from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.issue_solver import IssueSolver


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    solver = IssueSolver(root)
    attempt = solver.solve_once()
    payload = {
        "status": attempt.status,
        "diagnosis": asdict(attempt.diagnosis),
        "proposal_title": attempt.proposal.get("title") if attempt.proposal else None,
        "result": asdict(attempt.result) if attempt.result else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if attempt.status == "candidate_repaired" and attempt.result:
        branch = attempt.result.branch
        subprocess.run(["git", "push", "--set-upstream", "origin", branch], cwd=root, check=True)
        title = f"Genesis self-heal: {attempt.proposal.get('title', 'repair')}"
        body = (
            "Genesis detected a failing test state, produced this bounded repair candidate, "
            "and reran the full test suite successfully.\n\n"
            f"Diagnosis: `{attempt.diagnosis.category}` — {attempt.diagnosis.summary}\n\n"
            "This PR must still pass the independent validator quorum before promotion."
        )
        subprocess.run(
            ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body],
            cwd=root,
            check=False,
            env={**os.environ},
        )
    elif attempt.status == "needs_new_capability":
        title = f"Genesis capability gap: {attempt.diagnosis.category}"
        body = (
            "Genesis detected an issue it could not safely repair with its current bounded capabilities.\n\n"
            f"Diagnosis: {attempt.diagnosis.summary}\n\n"
            "The dynamic AI team should add or route to an appropriate specialist/provider. "
            "No unsafe code change was made."
        )
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], cwd=root, check=False, env={**os.environ})


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.issue_solver import IssueSolver
from genesis.providers import ProviderRegistry
from genesis.team import AITeam, AgentRole, DEFAULT_TEAM


SOFTWARE_DEBUGGER = AgentRole(
    "specialist_software_debugging",
    "Diagnose failing tests, regressions, imports, runtime errors, and bounded repair options",
    "Prefer root-cause fixes. Do not weaken validation, disable tests, change protected Genesis identity files, or approve your own repair.",
    dynamic=True,
    capability="software_debugging",
)


def run_issue_team(attempt) -> list[dict]:
    if attempt.status in {"healthy", "escalation_required"}:
        return []
    team = AITeam(
        ProviderRegistry(),
        roles=DEFAULT_TEAM + (SOFTWARE_DEBUGGER,),
    )
    return team.run_task(
        f"Diagnose and repair Genesis software issue: {attempt.diagnosis.category}",
        attempt.diagnosis.failure_text[-12000:],
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    solver = IssueSolver(root)
    attempt = solver.solve_once()
    team_output = run_issue_team(attempt)
    payload = {
        "status": attempt.status,
        "diagnosis": asdict(attempt.diagnosis),
        "proposal_title": attempt.proposal.get("title") if attempt.proposal else None,
        "result": asdict(attempt.result) if attempt.result else None,
        "issue_team_members": [item.get("agent") for item in team_output],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if attempt.status == "candidate_repaired" and attempt.result:
        branch = attempt.result.branch
        subprocess.run(["git", "push", "--set-upstream", "origin", branch], cwd=root, check=True)
        title = f"Genesis self-heal: {attempt.proposal.get('title', 'repair')}"
        body = (
            "Genesis detected a failing test state, assembled an issue-response AI team, produced this bounded repair candidate, "
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
    elif attempt.status in {"needs_new_capability", "escalation_required"}:
        title = f"Genesis capability gap: {attempt.diagnosis.category}"
        debugger_present = any(item.get("agent") == "specialist_software_debugging" for item in team_output)
        body = (
            "Genesis detected an issue it could not safely repair with its current bounded repair mechanisms.\n\n"
            f"Diagnosis: {attempt.diagnosis.summary}\n\n"
            f"Software-debugging specialist assembled: {debugger_present}.\n\n"
            "The issue-response team may route to a stronger configured Genesis Provider Protocol endpoint for a structured patch. "
            "No unsafe code change was made."
        )
        # Persist the escalation as a GitHub issue instead of relying on the
        # ephemeral runner's SQLite state. Avoid repeated identical open issues.
        if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN")):
            existing = subprocess.run(
                ["gh", "issue", "list", "--repo", os.environ["GITHUB_REPOSITORY"],
                 "--state", "open", "--limit", "100", "--json", "title",
                 "--jq", f'[.[] | select(.title == {json.dumps(title)})] | length'],
                cwd=root, check=False, text=True, capture_output=True, env={**os.environ},
            )
            if existing.returncode != 0:
                raise RuntimeError("Cannot check existing escalation issues; declining to create duplicate")
            if existing.stdout.strip() == "0":
                subprocess.run(
                    ["gh", "issue", "create", "--repo", os.environ["GITHUB_REPOSITORY"],
                     "--title", title, "--body", body],
                    cwd=root, check=True, env={**os.environ},
                )
        else:
            print(json.dumps({"status": "escalation_not_published", "reason": "GitHub environment unavailable"}))


if __name__ == "__main__":
    main()

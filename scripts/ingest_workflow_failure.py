from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.problem_solver import AutonomousProblemSolver


def _failed_logs(repository: str, run_id: str) -> str:
    if not run_id or not repository:
        return ""
    completed = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", repository, "--log-failed"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ},
    )
    text = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    return text[-50000:]


def ingest(
    root: Path,
    *,
    repository: str,
    run_id: str,
    workflow: str,
    conclusion: str,
    head_branch: str,
    head_sha: str,
    logs: str | None = None,
) -> dict:
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
    evidence = logs if logs is not None else _failed_logs(repository, run_id)
    summary = f"GitHub Actions workflow {workflow!r} concluded {conclusion!r} for {repository} run {run_id}."
    task, created = queue.create_unique(
        f"workflow-failure:{repository}:{run_id}",
        f"Diagnose and repair failed workflow: {workflow}",
        module_id="genesis.coding",
        priority=95,
        payload={
            "source": "github_actions",
            "repository": repository,
            "workflow": workflow,
            "run_id": run_id,
            "conclusion": conclusion,
            "head_branch": head_branch,
            "head_sha": head_sha,
            "use_ai_team": True,
            "repair_target": "candidate_branch" if head_branch and head_branch != "main" else "main",
        },
        max_attempts=5,
    )
    if created:
        task = queue.record_failure(
            task.task_id,
            summary,
            classification="workflow_failure",
            retry_after_seconds=0,
            module_id="genesis.coding",
        )
    solver = AutonomousProblemSolver(root)
    result = solver.solve_step(task, evidence=[summary, evidence[-20000:]])
    payload = {
        "task_created": created,
        "task_id": task.task_id,
        "workflow": workflow,
        "run_id": run_id,
        "head_branch": head_branch,
        "head_sha": head_sha,
        "gaps": result,
    }
    (runtime / "workflow_failure_diagnosis.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GENESIS_UPSTREAM_RUN_ID", ""))
    parser.add_argument("--workflow", default=os.environ.get("GENESIS_UPSTREAM_WORKFLOW", "unknown"))
    parser.add_argument("--conclusion", default=os.environ.get("GENESIS_UPSTREAM_CONCLUSION", "failure"))
    parser.add_argument("--head-branch", default=os.environ.get("GENESIS_UPSTREAM_HEAD_BRANCH", ""))
    parser.add_argument("--head-sha", default=os.environ.get("GENESIS_UPSTREAM_HEAD_SHA", ""))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    payload = ingest(
        root,
        repository=args.repository,
        run_id=args.run_id,
        workflow=args.workflow,
        conclusion=args.conclusion,
        head_branch=args.head_branch,
        head_sha=args.head_sha,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

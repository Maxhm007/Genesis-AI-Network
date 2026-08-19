from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop
from genesis.modules.task_queue import PersistentTaskQueue


DEVLAB_MARKER = "<!-- genesis-devlab-task -->"
TARGET_RE = re.compile(r"^DevLab-Target:\s*(.+?)\s*$", re.I | re.M)
MODULE_RE = re.compile(r"^DevLab-Module:\s*(genesis\.[\w.]+)\s*$", re.I | re.M)


def _github_open_issues() -> list[dict]:
    """Read open issues even when a workflow forgot to export GITHUB_TOKEN.

    Genesis-AI-Network is public, so read-only issue intake can safely use the
    public GitHub API without authentication. When a token is available it is
    used to gain the normal authenticated rate limit. GITHUB_REPOSITORY is a
    standard Actions environment variable and remains required so Genesis never
    guesses which repository should feed engineering work.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        return []
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Genesis-DevLab-Intake",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []


def ingest_devlab_issues(root: Path) -> list[str]:
    """Queue explicitly owner-marked GitHub issues for bounded DevLab execution.

    Issue intake only supplies the task. The resulting development cycle remains
    owner-initiated and must not be credited as Genesis-autonomous discovery.
    """
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    created: list[str] = []
    for issue in _github_open_issues():
        if issue.get("pull_request"):
            continue
        body = str(issue.get("body") or "")
        if DEVLAB_MARKER not in body:
            continue
        number = int(issue.get("number") or 0)
        target_match = TARGET_RE.search(body)
        if number <= 0 or target_match is None:
            continue
        target = target_match.group(1).strip().replace("\\", "/").lstrip("./")
        target_path = (root / target).resolve()
        try:
            target_path.relative_to(root.resolve())
        except ValueError:
            continue
        if not target_path.is_file():
            continue
        module_match = MODULE_RE.search(body)
        module_id = module_match.group(1).strip().lower() if module_match else "genesis.coding"
        objective = (
            f"Resolve GitHub issue #{number}: {str(issue.get('title') or '').strip()}. "
            f"Use the issue acceptance requirements as authoritative task context.\n\n{body[:8000]}"
        )
        task, was_created = queue.create_unique(
            f"github-devlab-issue:{number}",
            objective,
            module_id=module_id,
            priority=95,
            max_attempts=5,
            payload={
                "task_type": "devlab_issue",
                "executor": "genesis.devlab",
                "target_path": target,
                "context_paths": [target],
                "acceptance": body[:8000],
                "github_issue_number": number,
                "source": "owner_marked_github_issue",
                "attribution": "owner_initiated",
                "golden_path": True,
            },
        )
        if was_created:
            created.append(task.task_id)
    return created


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    created = ingest_devlab_issues(root)
    result = EfficientAutonomousEngineeringLoop(root).run_once()
    result["devlab_issue_intake"] = {"created_tasks": created, "count": len(created)}
    print(json.dumps(result, indent=2, sort_keys=True))

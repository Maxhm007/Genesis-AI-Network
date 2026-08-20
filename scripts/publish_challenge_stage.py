from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_BRANCH = "genesis/challenge-diagnostics-v3"
STAGES = {"provider_starting", "provider_ready", "devlab_running", "worker_complete", "terminal"}


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        text=True,
        capture_output=True,
    )


def stage_payload(*, stage: str, run_id: str, event: str, trigger_sha: str) -> dict[str, str]:
    if stage not in STAGES:
        raise ValueError(f"unsupported challenge stage: {stage}")
    return {
        "stage": stage,
        "run_id": str(run_id),
        "event": str(event),
        "trigger_sha": str(trigger_sha),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def publish_stage(
    root: Path,
    *,
    stage: str,
    run_id: str,
    event: str,
    trigger_sha: str,
    branch: str = DEFAULT_BRANCH,
) -> None:
    payload = stage_payload(stage=stage, run_id=run_id, event=event, trigger_sha=trigger_sha)
    _git(root, "fetch", "origin", "main")
    with tempfile.TemporaryDirectory(prefix="genesis-stage-") as temp_dir:
        worktree = Path(temp_dir) / "repo"
        _git(root, "worktree", "add", "--detach", str(worktree), "origin/main")
        try:
            _git(worktree, "checkout", "-B", branch)
            _git(worktree, "config", "user.name", "Genesis AI Diagnostics")
            _git(worktree, "config", "user.email", "genesis-ai@users.noreply.github.com")
            destination = worktree / "docs" / "runtime" / "GENESIS_CHALLENGE_STAGE.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _git(worktree, "add", "docs/runtime/GENESIS_CHALLENGE_STAGE.json")
            if _git(worktree, "diff", "--cached", "--quiet", check=False).returncode != 0:
                _git(worktree, "commit", "-m", f"Record Genesis challenge stage {stage} for run {run_id}")
            _git(worktree, "push", "--force", "origin", f"HEAD:refs/heads/{branch}")
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree), check=False)
            _git(root, "worktree", "prune", check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--trigger-sha", required=True)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    args = parser.parse_args()
    publish_stage(
        Path(__file__).resolve().parents[1],
        stage=args.stage,
        run_id=args.run_id,
        event=args.event,
        trigger_sha=args.trigger_sha,
        branch=args.branch,
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from genesis.issue_governor import (
    backlog_health,
    count_recent_velocity,
    equivalent_issue,
    publication_decision,
)


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "runtime" / "deferred_issue_candidates.json"
EVIDENCE_PATH = ROOT / "runtime" / "deferred_issue_release.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _load_queue(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _save_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows[-500:], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _list_issues(repository: str) -> list[dict]:
    result = _run([
        "gh", "issue", "list",
        "--repo", repository,
        "--state", "all",
        "--limit", "10000",
        "--json", "number,title,body,state,url,labels,createdAt,closedAt",
    ])
    if result.returncode != 0:
        raise RuntimeError(f"GitHub issue lookup failed: {result.stderr[-1200:]}")
    rows = json.loads(result.stdout or "[]")
    return rows if isinstance(rows, list) else []


def release_one(repository: str, *, queue_path: Path = QUEUE_PATH) -> dict:
    queue = _load_queue(queue_path)
    if not queue:
        return {"status": "idle", "queued_candidates": 0}

    issues = _list_issues(repository)
    open_count, opened_24h, closed_24h = count_recent_velocity(issues)
    health = backlog_health(
        open_count=open_count,
        opened_24h=opened_24h,
        closed_24h=closed_24h,
        healthy_limit=int(os.environ.get("GENESIS_ISSUE_HEALTHY_LIMIT", "25")),
        warning_limit=int(os.environ.get("GENESIS_ISSUE_WARNING_LIMIT", "50")),
    )

    # Highest-value candidate first; stable title tie-break keeps selection deterministic.
    ordered = sorted(
        queue,
        key=lambda row: (-float(row.get("value_score") or 0.0), str(row.get("title") or "")),
    )
    retained = list(queue)
    for candidate in ordered:
        relation, existing = equivalent_issue(
            issues,
            problem_fp=str(candidate.get("problem_fingerprint") or ""),
            occurrence_fp=str(candidate.get("occurrence_fingerprint") or ""),
        )
        if existing is not None:
            retained.remove(candidate)
            _save_queue(queue_path, retained)
            return {
                "status": "deduplicated_deferred_candidate",
                "relation": relation,
                "issue_number": existing.get("number"),
                "queued_candidates": len(retained),
                "backlog": health.__dict__,
            }

        severity = str(candidate.get("severity") or "medium")
        decision = publication_decision(
            health=health,
            value_score=float(candidate.get("value_score") or 0.0),
            severity=severity,
            bypass_labels=candidate.get("labels") or (),
        )
        if decision != "publish":
            continue

        title = str(candidate.get("title") or "").strip()
        body = str(candidate.get("body") or "").strip()
        if not title or not body:
            retained.remove(candidate)
            _save_queue(queue_path, retained)
            return {
                "status": "discarded_invalid_candidate",
                "queued_candidates": len(retained),
                "backlog": health.__dict__,
            }

        args = ["gh", "issue", "create", "--repo", repository, "--title", title, "--body", body]
        labels = [str(x).strip() for x in candidate.get("labels") or [] if str(x).strip()]
        if labels:
            args += ["--label", ",".join(labels)]
        created = _run(args)
        if created.returncode != 0:
            raise RuntimeError(f"GitHub deferred issue creation failed: {created.stderr[-1200:]}")
        retained.remove(candidate)
        _save_queue(queue_path, retained)
        url = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else ""
        match = re.search(r"/issues/(\d+)", url)
        return {
            "status": "released_deferred_candidate",
            "issue_number": int(match.group(1)) if match else None,
            "issue_url": url,
            "value_score": float(candidate.get("value_score") or 0.0),
            "queued_candidates": len(retained),
            "backlog": health.__dict__,
        }

    return {
        "status": "held_by_backlog_governor",
        "queued_candidates": len(queue),
        "backlog": health.__dict__,
    }


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository:
        raise SystemExit("GITHUB_REPOSITORY is required")
    result = release_one(repository)
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

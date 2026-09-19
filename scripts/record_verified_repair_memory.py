from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

from genesis.memory import GenesisMemory
from scripts.github_memory_sync import decode_memory_marker, encode_memory_marker


ROOT = Path(__file__).resolve().parents[1]


def _api(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/verified-memory",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else None


def _failure_summary(evidence: dict) -> list[dict]:
    rows = evidence.get("repair_memory")
    if not isinstance(rows, list):
        return []
    result: list[dict] = []
    for row in rows[-6:]:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "provider": str(row.get("provider") or "unknown")[:200],
                "outcome": str(row.get("outcome") or "unknown")[:200],
                "validation": str(row.get("validation") or "")[:500],
            }
        )
    return result


def record(
    repository: str,
    token: str,
    *,
    issue_number: int,
    target: str,
    candidate_sha: str,
    promoted_sha: str,
    worker_run: str,
    evidence_path: Path,
    root: Path = ROOT,
) -> dict:
    issue = _api(repository, token, "GET", f"/issues/{int(issue_number)}")
    if not isinstance(issue, dict):
        raise RuntimeError("GitHub issue could not be loaded")

    evidence = {}
    if evidence_path.is_file():
        loaded = json.loads(evidence_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            evidence = loaded

    diagnosis = evidence.get("diagnosis") if isinstance(evidence.get("diagnosis"), dict) else {}
    problem_class = str(diagnosis.get("category") or "github_reported_issue")
    root_cause = str(diagnosis.get("summary") or issue.get("title") or "verified repository defect")
    provider = str(evidence.get("provider") or "genesis-bounded-repair")

    memory = GenesisMemory(root)
    item = memory.remember_verified_repair(
        issue_number=int(issue_number),
        issue_title=str(issue.get("title") or f"Issue #{int(issue_number)}"),
        target=target,
        problem_class=problem_class,
        root_cause=root_cause,
        promoted_sha=promoted_sha,
        candidate_sha=candidate_sha,
        worker_run=worker_run,
        provider=provider,
        failed_approaches=_failure_summary(evidence),
    )
    portable = memory.store.portable_payload(item.memory_id)

    comments = _api(repository, token, "GET", f"/issues/{int(issue_number)}/comments?per_page=100") or []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        existing = decode_memory_marker(str(comment.get("body") or ""))
        if not isinstance(existing, dict):
            continue
        record_data = existing.get("record")
        if isinstance(record_data, dict) and record_data.get("memory_id") == item.memory_id:
            return {"status": "already_recorded", "memory_id": item.memory_id}

    marker = encode_memory_marker(portable)
    _api(
        repository,
        token,
        "POST",
        f"/issues/{int(issue_number)}/comments",
        {
            "body": (
                f"{marker}\n"
                "**Genesis verified repair memory**\n\n"
                f"- Memory ID: `{item.memory_id}`\n"
                f"- Target: `{target}`\n"
                f"- Promoted SHA: `{promoted_sha}`\n"
                f"- Worker run: `{worker_run}`\n"
                "- Trust rule: imported only from verified closed Issues and trusted repository authors/bots; "
                "memory remains evidence, never authority."
            )
        },
    )
    return {"status": "recorded", "memory_id": item.memory_id, "portable": portable}


def main() -> None:
    parser = argparse.ArgumentParser(description="Record one verified autonomous repair into durable Genesis memory")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--promoted-sha", required=True)
    parser.add_argument("--worker-run", required=True)
    parser.add_argument("--evidence-file", type=Path, default=ROOT / "runtime" / "github_issue_autorepair.json")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not args.repository or not token:
        raise SystemExit("repository and GitHub token are required")
    result = record(
        args.repository,
        token,
        issue_number=args.issue_number,
        target=args.target,
        candidate_sha=args.candidate_sha,
        promoted_sha=args.promoted_sha,
        worker_run=args.worker_run,
        evidence_path=args.evidence_file,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

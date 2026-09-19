from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from genesis.memory import GenesisMemory, contains_sensitive_material
from scripts.github_memory_sync import decode_memory_marker, encode_memory_marker
from scripts.record_verified_repair_memory import _api, _ensure_memory_label


ROOT = Path(__file__).resolve().parents[1]


def record_decision(
    repository: str,
    token: str,
    *,
    issue_number: int,
    decision_id: str,
    topic: str,
    rationale: str,
    evidence: dict,
    root: Path = ROOT,
) -> dict:
    issue = _api(repository, token, "GET", f"/issues/{int(issue_number)}")
    if not isinstance(issue, dict):
        raise RuntimeError("GitHub issue could not be loaded")
    labels = {
        str(row.get("name") or "")
        for row in (issue.get("labels") or [])
        if isinstance(row, dict)
    }
    if str(issue.get("state") or "").lower() != "closed" or "genesis-verified" not in labels:
        raise ValueError("architectural decision memory requires a closed genesis-verified issue")
    if contains_sensitive_material((topic, rationale, evidence)):
        raise ValueError("architectural decision contains sensitive material")

    memory = GenesisMemory(root)
    item = memory.remember_verified_decision(
        decision_id=decision_id,
        topic=topic,
        rationale=rationale,
        source_ref=f"issue:{int(issue_number)}",
        evidence={
            "issue_number": int(issue_number),
            **dict(evidence or {}),
        },
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

    _ensure_memory_label(repository, token, int(issue_number))
    marker = encode_memory_marker(portable)
    _api(
        repository,
        token,
        "POST",
        f"/issues/{int(issue_number)}/comments",
        {
            "body": (
                f"{marker}\n"
                "**Genesis verified architectural decision memory**\n\n"
                f"- Decision ID: {decision_id}\n"
                f"- Memory ID: {item.memory_id}\n"
                "- Source authority: closed genesis-verified issue.\n"
                "- Memory is reusable evidence; current repository state and governance remain authoritative."
            )
        },
    )
    return {"status": "recorded", "memory_id": item.memory_id, "portable": portable}


def main() -> None:
    parser = argparse.ArgumentParser(description="Record one verified Genesis architectural decision into durable memory")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--evidence-json", default="{}")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not args.repository or not token:
        raise SystemExit("repository and GitHub token are required")
    evidence = json.loads(args.evidence_json)
    if not isinstance(evidence, dict):
        raise SystemExit("evidence-json must decode to an object")
    result = record_decision(
        args.repository,
        token,
        issue_number=args.issue_number,
        decision_id=args.decision_id,
        topic=args.topic,
        rationale=args.rationale,
        evidence=evidence,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

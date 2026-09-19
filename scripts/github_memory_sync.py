from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from genesis.memory import GenesisMemory


ROOT = Path(__file__).resolve().parents[1]
MARKER_PREFIX = "<!-- genesis-verified-memory-v1:"
MARKER_RE = re.compile(r"<!-- genesis-verified-memory-v1:([A-Za-z0-9_-]+) -->")
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
TRUSTED_BOT_LOGINS = {"github-actions[bot]"}


def _api(repository: str, token: str, path: str):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Genesis-AI-Network/memory-sync",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else None


def encode_memory_marker(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{MARKER_PREFIX}{token} -->"


def decode_memory_marker(body: str) -> dict | None:
    match = MARKER_RE.search(str(body or ""))
    if not match:
        return None
    token = match.group(1)
    token += "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def trusted_memory_comment(comment: dict) -> bool:
    association = str(comment.get("author_association") or "").upper()
    login = str((comment.get("user") or {}).get("login") or "")
    return association in TRUSTED_ASSOCIATIONS or login in TRUSTED_BOT_LOGINS


def hydrate_payloads(memory: GenesisMemory, payloads: list[dict]) -> dict:
    ordered = sorted(
        [payload for payload in payloads if isinstance(payload, dict)],
        key=lambda payload: str((payload.get("record") or {}).get("created_at") or ""),
        reverse=True,
    )
    imported = 0
    ignored = 0
    current_by_key: dict[str, str] = {}
    for payload in ordered:
        try:
            before = memory.store.stats()["total"]
            item = memory.store.import_portable(payload)
            if memory.store.stats()["total"] > before:
                imported += 1
            key = str(item.metadata.get("knowledge_key") or "").strip()
            if not key:
                continue
            winner = current_by_key.get(key)
            if winner is None:
                current_by_key[key] = item.memory_id
                memory.store.supersede_knowledge_key(
                    key,
                    keep_memory_id=item.memory_id,
                    evidence={
                        "reason": "newest durable memory hydrated for knowledge key",
                        "replacement_memory_id": item.memory_id,
                    },
                )
            elif item.memory_id != winner and item.state == "validated":
                memory.store.transition(
                    item.memory_id,
                    "superseded",
                    evidence={
                        "reason": "newer durable memory already hydrated",
                        "replacement_memory_id": winner,
                    },
                )
        except (KeyError, TypeError, ValueError):
            ignored += 1
    memory.store.prune()
    return {"imported": imported, "ignored": ignored}


def sync(repository: str, token: str, *, root: Path = ROOT, max_issues: int = 100) -> dict:
    limit = max(1, min(int(max_issues), 200))
    query = urllib.parse.quote(f"repo:{repository} is:issue is:closed label:genesis-verified label:genesis-memory")
    url = f"https://api.github.com/search/issues?q={query}&sort=updated&order=desc&per_page=100"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Genesis-AI-Network/memory-sync",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        search = json.loads(response.read().decode("utf-8"))

    memory = GenesisMemory(root)
    payloads: list[dict] = []
    issues_seen = 0
    for issue in list(search.get("items") or [])[:limit]:
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        issues_seen += 1
        comments = _api(repository, token, f"/issues/{number}/comments?per_page=100") or []
        for comment in comments:
            if not isinstance(comment, dict) or not trusted_memory_comment(comment):
                continue
            payload = decode_memory_marker(str(comment.get("body") or ""))
            if payload is not None:
                payloads.append(payload)

    hydrated = hydrate_payloads(memory, payloads)
    return {
        "status": "ok",
        "issues_seen": issues_seen,
        **hydrated,
        **memory.store.stats(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Hydrate Genesis validated memory from verified GitHub Issues")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--max-issues", type=int, default=100)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not args.repository or not token:
        raise SystemExit("repository and GitHub token are required")
    print(json.dumps(sync(args.repository, token, max_issues=args.max_issues), sort_keys=True))


if __name__ == "__main__":
    main()

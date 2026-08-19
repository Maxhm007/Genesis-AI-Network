from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from self_evaluation_dashboard import build as build_self_evaluation

OWNER = "Maxhm007"
REPO = "Genesis-AI-Network"
CHAT_ISSUE = 52
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
OUT = Path("docs/status/chat.json")


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "genesis-gene-chat-snapshot",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def clean_body(body: str) -> str:
    return (
        str(body or "")
        .replace("<!-- genesis-gene-reply:v1 -->", "")
        .replace("**Gene 0**", "")
        .strip()
    )


def main() -> None:
    issue = api(f"/repos/{OWNER}/{REPO}/issues/{CHAT_ISSUE}")
    comments = api(f"/repos/{OWNER}/{REPO}/issues/{CHAT_ISSUE}/comments?per_page=100")
    messages = []
    for comment in comments[-60:]:
        user = comment.get("user") or {}
        login = str(user.get("login") or "unknown")
        body = str(comment.get("body") or "")
        is_gene = "genesis-gene-reply:v1" in body or login == "github-actions[bot]"
        messages.append(
            {
                "id": comment.get("id"),
                "role": "gene" if is_gene else "owner",
                "gene": "0" if is_gene else None,
                "author": "Gene 0" if is_gene else login,
                "body": clean_body(body),
                "created_at": comment.get("created_at"),
                "updated_at": comment.get("updated_at"),
                "url": comment.get("html_url"),
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thread": {
            "issue_number": CHAT_ISSUE,
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "state": issue.get("state"),
        },
        "messages": messages,
        "transport": {
            "read": "GitHub Pages chat.json snapshot",
            "write": "GitHub issue #52 owner comment",
            "reply": "guarded Genesis Gene Chat GitHub Actions workflow",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    self_eval = build_self_evaluation()
    print(f"Wrote {OUT} with {len(messages)} messages; self-development completed={self_eval['completed_self_development_tasks']}")


if __name__ == "__main__":
    main()

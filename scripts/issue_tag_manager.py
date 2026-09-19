from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from genesis.issue_tag_manager import (
    GENESIS_LABELS,
    LABEL_ALIASES,
    canonicalize_issue_tags,
    retired_genesis_labels,
)

def request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "genesis-issue-tag-manager",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed: HTTP {exc.code}: {body[:300]}") from exc

def issues(repository: str, token: str, event_issue: str) -> list[dict]:
    if event_issue.isdigit():
        row = request(repository, token, "GET", f"/issues/{event_issue}")
        return [row] if isinstance(row, dict) and "pull_request" not in row else []
    rows = request(repository, token, "GET", "/issues?state=all&sort=updated&direction=desc&per_page=100")
    return [row for row in rows if isinstance(row, dict) and "pull_request" not in row]

def all_issue_labels(repository: str, token: str) -> set[str]:
    rows = request(repository, token, "GET", "/issues?state=all&sort=updated&direction=desc&per_page=100")
    names: set[str] = set()
    for issue in rows if isinstance(rows, list) else []:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        for label in issue.get("labels") or []:
            if isinstance(label, dict):
                name = str(label.get("name") or "").strip()
                if name:
                    names.add(name)
    return names

def repository_labels(repository: str, token: str) -> list[dict]:
    rows = request(repository, token, "GET", "/labels?per_page=100")
    return rows if isinstance(rows, list) else []

def add_labels(repository: str, token: str, number: int, labels: tuple[str, ...]) -> None:
    if labels:
        request(repository, token, "POST", f"/issues/{number}/labels", {"labels": list(labels)})

def remove_label(repository: str, token: str, number: int, label: str) -> None:
    try:
        request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise

def ensure_registry(repository: str, token: str) -> dict:
    existing_rows = repository_labels(repository, token)
    existing = {str(row.get("name") or ""): row for row in existing_rows if isinstance(row, dict)}
    created: list[str] = []
    updated: list[str] = []

    for name, (color, description) in GENESIS_LABELS.items():
        row = existing.get(name)
        if row is None:
            request(repository, token, "POST", "/labels", {
                "name": name, "color": color, "description": description,
            })
            created.append(name)
            continue
        current_color = str(row.get("color") or "").lower()
        current_description = str(row.get("description") or "")
        if current_color != color.lower() or current_description != description:
            encoded = urllib.parse.quote(name, safe="")
            request(repository, token, "PATCH", f"/labels/{encoded}", {
                "new_name": name, "color": color, "description": description,
            })
            updated.append(name)

    return {"created": created, "updated": updated}

def migrate_aliases(repository: str, token: str, rows: list[dict]) -> list[dict]:
    changes: list[dict] = []
    for issue in rows:
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        plan = canonicalize_issue_tags(issue)
        if not plan.add and not plan.remove:
            continue
        add_labels(repository, token, number, plan.add)
        for label in plan.remove:
            remove_label(repository, token, number, label)
        changes.append({
            "issue": number, "add": plan.add, "remove": plan.remove, "reason": plan.reason,
        })
    return changes

def retire_unused_labels(repository: str, token: str) -> list[str]:
    existing = {str(row.get("name") or "") for row in repository_labels(repository, token) if isinstance(row, dict)}
    used = all_issue_labels(repository, token)
    retired: list[str] = []
    for name in retired_genesis_labels(existing, used):
        encoded = urllib.parse.quote(name, safe="")
        request(repository, token, "DELETE", f"/labels/{encoded}")
        retired.append(name)
    return retired

def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    event_issue = os.environ.get("EVENT_ISSUE", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    registry = ensure_registry(repository, token)
    rows = issues(repository, token, event_issue)
    changes = migrate_aliases(repository, token, rows)

    # Full repository retirement is schedule/manual/push only. Event runs remain
    # narrowly scoped so label churn on one issue cannot trigger broad deletion.
    retired: list[str] = []
    if not event_issue:
        retired = retire_unused_labels(repository, token)

    print(json.dumps({
        "status": "ok",
        "registry": registry,
        "changes": changes,
        "change_count": len(changes),
        "retired": retired,
        "retired_count": len(retired),
        "aliases": LABEL_ALIASES,
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

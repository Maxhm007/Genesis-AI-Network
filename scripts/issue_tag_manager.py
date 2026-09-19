from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from genesis.issue_tag_manager import canonicalize_issue_tags

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

def add_labels(repository: str, token: str, number: int, labels: tuple[str, ...]) -> None:
    if labels:
        request(repository, token, "POST", f"/issues/{number}/labels", {"labels": list(labels)})

def remove_label(repository: str, token: str, number: int, label: str) -> None:
    try:
        request(repository, token, "DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise

def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    event_issue = os.environ.get("EVENT_ISSUE", "").strip()
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    changed = []
    for issue in issues(repository, token, event_issue):
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        plan = canonicalize_issue_tags(issue)
        if not plan.add and not plan.remove:
            continue
        add_labels(repository, token, number, plan.add)
        for label in plan.remove:
            remove_label(repository, token, number, label)
        changed.append({"issue": number, "add": plan.add, "remove": plan.remove, "reason": plan.reason})
    print(json.dumps({"status": "ok", "changes": changed, "change_count": len(changed)}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

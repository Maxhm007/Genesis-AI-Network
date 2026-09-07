from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

SUCCESSOR_RE = re.compile(r"genesis-unsolved-successor-of:(\d+)", re.I)
DASHBOARD_MARKER_RE = re.compile(
    r"<!--\s*(genesis-dashboard-review:[0-9a-f]{16})\s*-->", re.I
)
FINGERPRINT_RE = re.compile(
    r"Genesis-Problem-Fingerprint:\s*(dashboard-review:[0-9a-f]{16})", re.I
)


def parent_issue_number(body: str) -> int | None:
    match = SUCCESSOR_RE.search(body or "")
    return int(match.group(1)) if match else None


def inherit_dashboard_identity(successor_body: str, parent_body: str) -> str:
    """Copy exact dashboard problem identity from a parent into its repair successor.

    The hourly dashboard reviewer suppresses duplicate findings by its exact
    genesis-dashboard-review fingerprint. Repair successors must retain that
    identity so the same unresolved objective cannot be recreated as a second
    open issue.
    """
    successor_body = successor_body or ""
    parent_body = parent_body or ""

    marker_match = DASHBOARD_MARKER_RE.search(parent_body)
    fingerprint_match = FINGERPRINT_RE.search(parent_body)
    inherited: list[str] = []

    if marker_match:
        marker = marker_match.group(1)
        if marker.lower() not in successor_body.lower():
            inherited.append(f"<!-- {marker} -->")

    if fingerprint_match:
        fingerprint = fingerprint_match.group(1)
        if fingerprint.lower() not in successor_body.lower():
            inherited.append(f"Genesis-Problem-Fingerprint: {fingerprint}")

    if not inherited:
        return successor_body

    base = successor_body.rstrip()
    separator = "\n\n" if base else ""
    inherited_text = "\n".join(inherited)
    return f"{base}{separator}{inherited_text}\n"


def _request_json(url: str, token: str, *, method: str = "GET", payload: dict | None = None) -> object:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/dashboard-successor-identity",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    event_path = Path(str(os.environ.get("GITHUB_EVENT_PATH") or "").strip())
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not event_path.is_file() or not token:
        print("GitHub event/token unavailable; no successor identity update performed.")
        return 0

    event = json.loads(event_path.read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    repository = event.get("repository") or {}
    repo = str(repository.get("full_name") or "").strip()
    issue_number = int(issue.get("number") or 0)
    successor_body = str(issue.get("body") or "")
    parent_number = parent_issue_number(successor_body)

    if not repo or not issue_number or parent_number is None:
        print("Opened issue is not a repair successor; nothing to inherit.")
        return 0

    parent = _request_json(
        f"https://api.github.com/repos/{repo}/issues/{parent_number}", token
    )
    if not isinstance(parent, dict):
        raise RuntimeError("GitHub returned an invalid parent issue response")

    updated_body = inherit_dashboard_identity(successor_body, str(parent.get("body") or ""))
    if updated_body == successor_body:
        print("Parent has no new dashboard identity to inherit.")
        return 0

    _request_json(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}",
        token,
        method="PATCH",
        payload={"body": updated_body},
    )
    print(f"Inherited dashboard identity from #{parent_number} into #{issue_number}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

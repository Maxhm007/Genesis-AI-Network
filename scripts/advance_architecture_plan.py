from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


PLAN_MARKER = "<!-- genesis-architecture-plan:"
ACTIVE_LABELS = (
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-solver-exhausted",
    "genesis-deferred",
    "genesis-blocked",
    "genesis-needs-routing",
    "genesis-qwen3-agentic",
)


def advance_body(body: str, completed_target: str) -> tuple[str, str]:
    text = str(body or "")
    if PLAN_MARKER not in text:
        return "complete", text
    step_match = re.search(r"(?m)^- \*\*Architecture step:\*\* `(\d+)/(\d+)`$", text)
    target_match = re.search(r"(?m)^- \*\*Target:\*\* `([^`]+)`$", text)
    next_match = re.search(r"(?m)^- \*\*Architecture next target:\*\* `([^`]+)`$", text)
    if step_match is None or target_match is None:
        return "complete", text
    current, total = int(step_match.group(1)), int(step_match.group(2))
    current_target = target_match.group(1).strip()
    if current_target != str(completed_target or "").strip():
        raise ValueError("completed target does not match current architecture plan target")
    if current >= total or next_match is None:
        return "complete", text

    next_target = next_match.group(1).strip()
    updated = re.sub(
        r"(?m)^- \*\*Architecture step:\*\* `\d+/\d+`$",
        f"- **Architecture step:** `{current + 1}/{total}`",
        text,
        count=1,
    )
    updated = re.sub(
        r"(?m)^- \*\*Target:\*\* `[^`]+`$",
        f"- **Target:** `{next_target}`",
        updated,
        count=1,
    )
    updated = re.sub(r"(?m)^- \*\*Architecture next target:\*\* `[^`]+`\n?", "", updated, count=1)
    updated = re.sub(r"(?m)^- \*\*Architecture new target:\*\* `[^`]+`\n?", "", updated, count=1)
    updated = re.sub(r"(?m)^- \*\*Task type:\*\* `architecture_expansion`\n?", "", updated, count=1)
    return "continued", updated


def _request(repository: str, token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/architecture-plan-advance",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        if method == "DELETE" and exc.code == 404:
            return {}
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {method} {path}: {detail}") from exc


def advance_issue(repository: str, token: str, issue_number: int, completed_target: str) -> dict:
    issue = _request(repository, token, "GET", f"/issues/{int(issue_number)}")
    body = str(issue.get("body") or "")
    status, updated = advance_body(body, completed_target)
    if status != "continued":
        return {"status": "complete", "issue_number": int(issue_number)}

    _request(repository, token, "PATCH", f"/issues/{int(issue_number)}", {"body": updated})
    for label in ACTIVE_LABELS:
        _request(
            repository,
            token,
            "DELETE",
            f"/issues/{int(issue_number)}/labels/{urllib.parse.quote(label, safe='')}",
        )
    _request(
        repository,
        token,
        "POST",
        f"/issues/{int(issue_number)}/labels",
        {"labels": ["genesis-autonomous", "agentic-lab", "genesis-architecture-route"]},
    )
    next_target = re.search(r"(?m)^- \*\*Target:\*\* `([^`]+)`$", updated).group(1)
    _request(
        repository,
        token,
        "POST",
        f"/issues/{int(issue_number)}/comments",
        {
            "body": (
                "<!-- genesis-architecture-step-advanced -->\n"
                f"Genesis verified and promoted architecture step for `{completed_target}`. "
                f"The same authoritative Issue now continues with next target `{next_target}`. "
                "The parent remains open until the final planned step is independently validated."
            )
        },
    )
    return {
        "status": "continued",
        "issue_number": int(issue_number),
        "completed_target": completed_target,
        "next_target": next_target,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--issue-number", required=True, type=int)
    parser.add_argument("--completed-target", required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN or GH_TOKEN is required")
    result = advance_issue(args.repository, token, args.issue_number, args.completed_target)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

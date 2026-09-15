from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import agentic_lab_capability_first_dispatch as legacy


ACTIVE_LABELS = {
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
}


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
            "User-Agent": "Genesis-AI-Network/fifo-router",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def _labels(issue: dict) -> set[str]:
    rows = set()
    for item in issue.get("labels") or []:
        rows.add(str(item.get("name") if isinstance(item, dict) else item))
    return rows


def _legacy_capability_performance_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    return (
        title.startswith("Genesis Control: Capability Growth")
        and "<!-- genesis-capability-source:" in body
        and "- **Benchmark:**" in body
        and "- **Validated baseline:**" in body
        and "- **Reference:**" in body
        and "Improve the measured Genesis capability gap" in body
    )


def _terminalize_performance_indicators(repository: str, token: str, issues: list[dict]) -> list[int]:
    closed: list[int] = []
    for issue in issues:
        if not _legacy_capability_performance_issue(issue):
            continue
        number = int(issue.get("number") or 0)
        if number <= 0:
            continue
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        if not title.startswith("[Performance Indicator]"):
            title = f"[Performance Indicator] {title}"[:240]
        if "<!-- genesis-performance-indicator -->" not in body:
            body = (
                body.rstrip()
                + "\n\n<!-- genesis-performance-indicator -->\n"
                + "### Performance indicator classification\n"
                + "Genesis classified this legacy capability-growth record as a changing benchmark measurement. It stays closed and must not enter DevLab, Issue Solver, Agentic Lab, Qwen3, DeepSeek, or repair retry lanes. Concrete defects or missing capabilities require a separate actionable issue.\n"
            )

        # Terminal state is authoritative. A saturated/locked comment thread must
        # never prevent performance-indicator classification from completing.
        updated = _request(
            repository,
            token,
            "PATCH",
            f"/issues/{number}",
            {
                "title": title,
                "body": body,
                "labels": ["performance-indicator"],
                "state": "closed",
                "state_reason": "not_planned",
            },
        )
        if not isinstance(updated, dict) or str(updated.get("state") or "").lower() != "closed":
            continue
        closed.append(number)

        try:
            _request(
                repository,
                token,
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": (
                        "<!-- genesis-performance-indicator-auto-close -->\n"
                        "Genesis Agentic FIFO terminal classification: this legacy capability-growth record is a performance indicator, not immediate repair work. "
                        "The benchmark value remains measurable over time; concrete defects must use separate actionable Issues. Closed as not planned and removed from Agentic repair lanes."
                    )
                },
            )
        except urllib.error.HTTPError as exc:
            print(json.dumps({"status": "comment_skipped", "issue_number": number, "http_status": exc.code}, sort_keys=True))
    return closed


def _actionable(issue: dict) -> bool:
    labels = _labels(issue)
    if "genesis-autonomous" not in labels or "genesis-verified" in labels:
        return False
    if labels & {"genesis-persistent", "duplicate", "invalid", "wontfix", "genesis-superseded", "performance-indicator"}:
        return False
    title = str(issue.get("title") or "").strip().lower()
    body = str(issue.get("body") or "").lower()
    if title.startswith(("[genesis gene chat]", "genesis chat:", "[genesis hourly report]", "[genesis ops]", "[performance indicator]")):
        return False
    if "persistent github-native reporting channel" in body or "<!-- genesis-performance-indicator -->" in body:
        return False
    return int(issue.get("number") or 0) > 1


def _open_fifo(repository: str, token: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 101):
        batch = _request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub issue response was not a list")
        rows.extend(row for row in batch if isinstance(row, dict) and not row.get("pull_request"))
        if len(batch) < 100:
            break
    return rows


def _is_android_issue(issue: dict) -> bool:
    text = (str(issue.get("title") or "") + "\n" + str(issue.get("body") or "")).lower()
    return "application_development" in text and "android" in text


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    issues = _open_fifo(repository, token)
    terminalized = _terminalize_performance_indicators(repository, token, issues)
    if terminalized:
        print(json.dumps({"status": "terminalized_performance_indicators", "issues": terminalized}, sort_keys=True))
        issues = _open_fifo(repository, token)

    actionable = [issue for issue in issues if _actionable(issue)]
    if not actionable:
        return legacy.main()

    oldest = actionable[0]
    if not _is_android_issue(oldest):
        return legacy.main()

    active = [int(issue.get("number") or 0) for issue in issues if _labels(issue) & ACTIVE_LABELS]
    if active:
        print(json.dumps({"status": "busy", "reason": "global_fifo_repair_lock", "active_issues": active}, sort_keys=True))
        return 0

    number = int(oldest.get("number") or 0)
    _request(repository, token, "POST", f"/issues/{number}/labels", {"labels": ["genesis-autonomous", "agentic-lab", "genesis-repair-in-progress"]})
    _request(
        repository,
        token,
        "POST",
        f"/actions/workflows/genesis-android-issue-worker.yml/dispatches",
        {"ref": "main", "inputs": {"issue_number": str(number)}},
    )
    _request(
        repository,
        token,
        "POST",
        f"/issues/{number}/comments",
        {"body": "<!-- genesis-android-fifo-dispatch -->\nGenesis strict FIFO routed this oldest Android application issue to the bounded mobile repair lane. The same Issue remains authoritative; no successor Issue was created."},
    )
    print(json.dumps({"status": "dispatched", "issue_number": number, "lane": "android_mobile_fifo"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

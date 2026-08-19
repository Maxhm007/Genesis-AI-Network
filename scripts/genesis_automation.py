from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from genesis.automation import GenesisAutomationModule
from genesis.operations import GenesisOperations
from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def _github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        print(f"GitHub escalation HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}")
        return None
    except Exception as exc:
        print(f"GitHub escalation unavailable: {type(exc).__name__}: {exc}")
        return None


def evaluate() -> dict:
    operations = GenesisOperations(ROOT).report()
    report = GenesisAutomationModule(ROOT, max_autonomous_attempts=2).evaluate(operations)
    print(json.dumps(report, sort_keys=True))
    return report


def sync_devlab_status() -> dict:
    """Publish the bounded DevLab stage/error to the issue that created the task.

    The reporting step runs after engineering in a workflow step that already has
    issue-write permission. It does not change task state, candidate state,
    validation, promotion, or attribution; it only exposes existing runtime
    evidence so failed attempts can be diagnosed without guessing.
    """
    path = RUNTIME / "autonomous_engineering.json"
    if not path.is_file():
        return {"status": "skipped", "reason": "autonomous engineering evidence unavailable"}
    try:
        engineering = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "skipped", "reason": f"invalid engineering evidence: {type(exc).__name__}"}

    queue = PersistentTaskQueue(RUNTIME / "genesis_tasks.sqlite3")
    posted: list[int] = []
    skipped: list[int] = []
    attempted_ids: set[str] = set()

    def post(task: dict, *, stage: str, method: str = "", error: str = "", devlab_attempt: int | None = None) -> None:
        payload = task.get("payload") or {}
        issue_number = int(payload.get("github_issue_number") or 0)
        task_id = str(task.get("task_id") or "")
        if issue_number <= 0 or not task_id:
            return
        attempt_number = devlab_attempt if devlab_attempt is not None else int(task.get("attempt_count") or 0)
        marker = f"<!-- genesis-devlab-status:{task_id}:{attempt_number}:{stage} -->"
        comments = _github_request("GET", f"/issues/{issue_number}/comments?per_page=100") or []
        if any(marker in str(comment.get("body") or "") for comment in comments):
            skipped.append(issue_number)
            return
        compact_error = str(error or "").strip()[-1800:]
        body = (
            f"{marker}\n"
            "### Genesis DevLab execution status\n\n"
            f"- **Task:** `{task_id}`\n"
            f"- **Stage:** `{stage}`\n"
            f"- **DevLab attempt:** {attempt_number}\n"
            f"- **Method:** `{method or 'not_started'}`\n"
            f"- **Task state before this attempt:** `{task.get('state', 'unknown')}`\n"
            f"- **Attribution:** `{payload.get('attribution', 'unknown')}`\n"
            f"- **Target:** `{payload.get('target_path', '')}`\n"
        )
        if compact_error:
            body += f"- **Observed failure/evidence:** `{compact_error}`\n"
        body += (
            "\nThis is execution evidence only. A task is not complete until the exact candidate passes tests, Security, independent validator quorum, promotion, and post-promotion verification."
        )
        made = _github_request("POST", f"/issues/{issue_number}/comments", {"body": body})
        if made:
            posted.append(issue_number)

    for attempt in engineering.get("attempted_tasks", []) or []:
        if not isinstance(attempt, dict) or attempt.get("executor_module") != "genesis.devlab":
            continue
        task = attempt.get("task") or {}
        task_id = str(task.get("task_id") or "")
        if task_id:
            attempted_ids.add(task_id)
        devlab = attempt.get("devlab") or {}
        retry = devlab.get("retry") or {}
        feedback = devlab.get("feedback") or {}
        candidate = attempt.get("candidate") or {}
        error = attempt.get("error") or feedback.get("failure") or candidate.get("message") or ""
        post(
            task,
            stage=str(attempt.get("coding_status") or devlab.get("status") or "unknown"),
            method=str(retry.get("method") or ""),
            error=str(error),
            devlab_attempt=int(retry.get("attempt") or (int(task.get("attempt_count") or 0) + 1)),
        )

    # If an owner-marked DevLab task exists but did not reach the executor this
    # cycle, expose that too. This distinguishes intake/selection failures from
    # provider/proposal failures.
    for state in ("new", "assigned", "failed", "blocked", "running", "review"):
        for queued in queue.list(state=state, limit=200):
            if queued.task_id in attempted_ids or str(queued.payload.get("executor") or "") != "genesis.devlab":
                continue
            post(
                {
                    "task_id": queued.task_id,
                    "state": queued.state,
                    "attempt_count": queued.attempt_count,
                    "payload": queued.payload,
                },
                stage="queued_not_attempted",
                error=str(queued.last_error or ""),
            )

    result = {"status": "ok", "posted": posted, "deduped": skipped}
    (RUNTIME / "devlab_issue_status_sync.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


def sync_escalations(report: dict | None = None) -> dict:
    report = report or json.loads((RUNTIME / "automation_report.json").read_text(encoding="utf-8"))
    operations = {row["issue_key"]: row for row in GenesisOperations(ROOT).report().get("issues", [])}
    existing = _github_request("GET", "/issues?state=all&per_page=100") or []
    by_key = {}
    marker_prefix = "<!-- genesis-chatgpt-escalation:"
    for issue in existing:
        if "pull_request" in issue:
            continue
        body = str(issue.get("body") or "")
        if marker_prefix in body:
            key = body.split(marker_prefix, 1)[1].split(" -->", 1)[0].strip()
            by_key[key] = issue

    created, updated, closed = [], [], []
    for decision in report.get("decisions", []):
        key = str(decision.get("issue_key", ""))
        current = by_key.get(key)
        item = operations.get(key, {})
        action = decision.get("action")
        if action == "resolved":
            if current and current.get("state") != "closed":
                changed = _github_request("PATCH", f"/issues/{current['number']}", {"state": "closed"})
                if changed:
                    closed.append(current["number"])
            continue
        if action != "escalate_chatgpt":
            continue

        marker = f"<!-- genesis-chatgpt-escalation:{key} -->"
        body = (
            f"{marker}\n"
            "Genesis could not resolve this issue within its bounded autonomous repair budget and requests ChatGPT engineering assistance.\n\n"
            f"- **Operational issue:** {item.get('title', decision.get('title'))}\n"
            f"- **Severity:** {item.get('severity', 'unknown')}\n"
            f"- **Module:** `{item.get('module_id', 'unknown')}`\n"
            f"- **Evidence:** {item.get('evidence', 'Unavailable')}\n"
            f"- **Recommended remediation:** {item.get('remediation', 'Investigate safely.')}\n"
            f"- **Genesis attempts:** {decision.get('attempts')}\n"
            f"- **Task:** `{decision.get('task_id')}`\n"
            f"- **Task state:** `{decision.get('task_state')}`\n"
            f"- **Escalation reason:** {decision.get('reason')}\n\n"
            "## Required handling\n"
            "Inspect repository state and relevant workflow evidence, apply only the smallest safe fix, and preserve the Genesis Constitution, Genesis Block, validation quorum, Security boundaries, owner control, signing policy, and secret boundaries. Do not close this issue until the fix is validated or the remaining blocker is explicitly documented.\n"
        )
        if current is None:
            made = _github_request("POST", "/issues", {
                "title": f"[Genesis Escalation] {item.get('title', decision.get('title'))}",
                "body": body,
            })
            if made:
                created.append(made.get("number"))
        else:
            patch = {"body": body}
            if current.get("state") == "closed":
                patch["state"] = "open"
            changed = _github_request("PATCH", f"/issues/{current['number']}", patch)
            if changed:
                updated.append(current["number"])

    result = {"status": "ok", "created": created, "updated": updated, "closed": closed}
    (RUNTIME / "chatgpt_escalation_sync.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Genesis bounded automation and ChatGPT escalation")
    parser.add_argument("action", choices=("evaluate", "sync", "all"))
    args = parser.parse_args()
    report = None
    if args.action in {"evaluate", "all"}:
        report = evaluate()
    if args.action in {"sync", "all"}:
        sync_devlab_status()
        sync_escalations(report)


if __name__ == "__main__":
    main()

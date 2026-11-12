"""Reciprocal recovery watchdog: Genesis repairs Eve workflows, Eve repairs Genesis.

Version 1 performs one bounded action per cycle:
* on first failure of a recent completed workflow: retry failed jobs once;
* on repeated failure: create a deduplicated repair ticket containing failed
  steps and immutable run URLs.

No peer chat, no speculative issue closure, no automatic merges. Target-repo
Actions+Issues write permissions are explicitly required. Never executes
incoming GitHub content. No local persistent state or model endpoint needed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPOSITORIES = {
    "genesis": "Maxhm007/Genesis-AI-Network",
    "eve": "Maxhm007/Eve",
}
MAX_AGE_HOURS = 48
MAX_RUNS = 30
EXCLUDED_NAMES = {"Eve independent peer research",
                  "Genesis independent Eve peer research"}
AGENT = "Reciprocal-Healer/1.0"
LIMIT = 512_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("GitHub redirect refused")


def _open(request, timeout=25):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)


class GitHub:
    def __init__(self, token, opener=None):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("PEER_HEAL_TOKEN is required (target-repo Actions and Issues write)")
        self.token = token
        self.opener = opener or _open

    def request(self, method, target, suffix, payload=None):
        if target not in REPOSITORIES or not suffix.startswith("/"):
            raise ValueError("Unknown target")
        if method not in {"GET", "POST"}:
            raise ValueError("Unsupported method")
        if method == "POST" and not (
            re.fullmatch(r"/actions/runs/[1-9]\d*/rerun-failed-jobs", suffix)
            or suffix == "/issues"
        ):
            raise ValueError("Write operation not allowed")
        is_search = method == "GET" and suffix.startswith("/search/issues?q=")
        if not (suffix.startswith("/actions/runs") or suffix.startswith("/issues") or is_search):
            raise ValueError("Unsupported resource")
        url = ("https://api.github.com" + suffix) if is_search else (
            "https://api.github.com/repos/" + REPOSITORIES[target] + suffix)
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": AGENT,
        }
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            if len(body) > 16_000:
                raise ValueError("Oversized mutation")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        with self.opener(request, timeout=25) as response:
            data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("Oversized GitHub response")
        return json.loads(data) if data.strip() else {}

    def failed_runs(self, target):
        data = self.request("GET", target, "/actions/runs?status=failure&per_page=" + str(MAX_RUNS))
        runs = data.get("workflow_runs")
        if not isinstance(runs, list) or len(runs) > MAX_RUNS:
            raise ValueError("Malformed workflow runs response")
        return runs

    def jobs(self, target, run_id):
        data = self.request("GET", target, "/actions/runs/{}/jobs?per_page=100".format(run_id))
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("Malformed jobs response")
        return jobs

    def find_ticket(self, target, exact_title):
        """Search all target issues (including closed), match exact title."""
        query = 'repo:{} in:title "{}"'.format(REPOSITORIES[target], exact_title)
        suffix = "/search/issues?q=" + urllib.parse.quote(query, safe="")
        data = self.request("GET", target, suffix)
        matches = data.get("items")
        if data.get("incomplete_results") or not isinstance(matches, list):
            raise ValueError("Incomplete issue search: refusing duplicate ticket")
        return any(isinstance(row, dict) and row.get("title") == exact_title for row in matches)

    def issue(self, target, title, description):
        return self.request("POST", target, "/issues", {"title": title, "body": description})

    def retry_failed(self, target, run_id):
        self.request("POST", target, "/actions/runs/{}/rerun-failed-jobs".format(run_id))


def select_failure(runs, now=None, max_age_hours=MAX_AGE_HOURS):
    """Choose a recent, actionable failure; no retry loops or old backlog."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    valid = []
    for item in runs:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("conclusion") != "failure" or item.get("status") != "completed":
                continue
            if item.get("name") in EXCLUDED_NAMES:
                continue
            ident = item.get("id")
            attempt = item.get("run_attempt")
            if type(ident) is not int or ident < 1 or type(attempt) is not int or attempt < 1:
                continue
            created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None or created < cutoff or created > now + timedelta(minutes=5):
                continue
            valid.append(item)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return sorted(valid, key=lambda r: (r["created_at"], r["id"]), reverse=True)


def diagnosis(run, jobs):
    """Evidence-only diagnosis, never pretend to know the root cause."""
    failed = []
    for job in jobs[:100]:
        if not isinstance(job, dict) or job.get("conclusion") != "failure":
            continue
        steps = job.get("steps") or []
        bad_steps = [str(s.get("name", "unknown"))[:120] for s in steps
                     if isinstance(s, dict) and s.get("conclusion") == "failure"][:10]
        failed.append({"job": str(job.get("name", "unknown"))[:120], "steps": bad_steps})
    return failed[:20]


def repair_ticket(run, failures, helper):
    title = "[Mutual Heal] workflow run {} failed after retry".format(run["id"])
    if helper not in REPOSITORIES:
        raise ValueError("Unknown healer")
    url = run.get("html_url", "")
    if not isinstance(url, str) or not url.startswith("https://github.com/"):
        url = "https://github.com/{}/actions/runs/{}".format(
            REPOSITORIES["eve" if helper == "genesis" else "genesis"], run["id"])
    body = (
        "## Reciprocal recovery: " + helper.title() + " → peer\n\n"
        "The peer watchdog detected a completed workflow failure after a bounded retry. "
        "**A verified code fix has NOT been applied.**\n\n"
        "- Workflow: " + str(run.get("name", "Unknown"))[:200] + "\n"
        "- Run: " + url + "\n"
        "- Attempts: " + str(run.get("run_attempt")) + "\n"
        "- GitHub run ID: " + str(run["id"]) + "\n\n"
        "### Failed jobs and steps (observed evidence)\n\n"
        "```json\n" + json.dumps(failures, ensure_ascii=False, indent=2)[:6000] + "\n```\n\n"
        "### Repair gate\n"
        "- [ ] Reproduce the failing step in an isolated environment\n"
        "- [ ] Identify root cause from logs rather than speculate\n"
        "- [ ] Prepare a minimal patch in a branch and open a PR\n"
        "- [ ] Execute regression tests and an independent review\n"
        "- [ ] Merge only after approved checks; confirm follow-up success\n\n"
        "No untrusted commands, peer chat, auto-merge or secret disclosure is authorized.\n"
    )
    return title, body


def heal_once(identity, api, now=None):
    """Each agent attempts at most one peer recovery action per cycle."""
    if identity not in REPOSITORIES:
        raise ValueError("Unknown healer identity")
    target = "eve" if identity == "genesis" else "genesis"
    eligible = select_failure(api.failed_runs(target), now)
    if not eligible:
        return {"status": "healthy_or_no_recent_failed_runs", "target": target}
    already_reported = False
    for run in eligible[:10]:
        attempt = run["run_attempt"]
        if attempt == 1:
            api.retry_failed(target, run["id"])
            return {"status": "recovery_retry_requested", "target": target,
                    "run_id": run["id"], "attempt": 1}
        title, body = repair_ticket(run, diagnosis(run, api.jobs(target, run["id"])), identity)
        if api.find_ticket(target, title):
            already_reported = True
            continue
        ticket = api.issue(target, title, body)
        return {"status": "repair_ticket_created", "target": target,
                "run_id": run["id"], "url": ticket.get("html_url")}
    return {"status": "repair_tickets_already_open" if already_reported else
            "no_actionable_failure", "target": target}


def main():
    parser = argparse.ArgumentParser(description="Mutual recovery: monitor and heal the other AI")
    parser.add_argument("--identity", required=True, choices=("genesis", "eve"))
    args = parser.parse_args()
    result = heal_once(args.identity, GitHub(os.getenv("PEER_HEAL_TOKEN", "")))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

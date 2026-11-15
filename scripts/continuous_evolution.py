"""Nexus-owned turn ledger, retaining existing Genesis issue-solver authority."""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

GENESIS = "Maxhm007/Genesis-AI-Network"
EVE = "Maxhm007/Eve"
ISSUE = 1212
START = "<!-- continuous-turn-state -->"
END = "<!-- /continuous-turn-state -->"
FENCE = chr(96) * 3
API = "https://api.github.com/repos/"
TIMEOUT_MINUTES = 40


def api(repo, suffix, method="GET", payload=None, token=""):
    if repo not in (GENESIS, EVE) or not suffix.startswith("/"):
        raise ValueError("Invalid repository path")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Genesis-Eve-Continuous/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if method != "GET" and (repo != GENESIS or not token):
        raise ValueError("Only Genesis may change the shared ledger")
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(
        urllib.request.Request(API + repo + suffix, method=method, headers=headers, data=data),
        timeout=20,
    ) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Oversized API response")
    return json.loads(raw) if raw else {}


def decode(body):
    if not isinstance(body, str) or body.count(START) != 1 or body.count(END) != 1:
        raise ValueError("Invalid turn ledger markers")
    between = body.split(START, 1)[1].split(END, 1)[0].strip()
    if not (between.startswith(FENCE + "json\n") and between.endswith(FENCE)):
        raise ValueError("Invalid turn ledger encoding")
    state = json.loads(between[len(FENCE) + 5:-len(FENCE)].strip())
    if (state.get("version") != 1 or type(state.get("sequence")) is not int or
            state["sequence"] < 1 or state.get("owner") not in ("genesis", "eve") or
            state.get("status") not in ("ready", "running")):
        raise ValueError("Unrecognized turn state")
    return state


def encode(body, state):
    prefix, trailing = body.split(START, 1)
    _, suffix = trailing.split(END, 1)
    return (prefix + START + "\n" + FENCE + "json\n" +
            json.dumps(state, sort_keys=True) + "\n" + FENCE + "\n" + END + suffix)


def deadline(value, now):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) < now
    except (ValueError, TypeError):
        return False


def ack_result(sequence, token=""):
    # A single durable Eve acknowledgement issue avoids unbounded issue spam.
    # This is an operational receipt, NOT authorization for automatic merges.
    # Use this run's repository-scoped GITHUB_TOKEN for public peer reads.
    # This avoids the 60/hour anonymous REST limit; api() still rejects every
    # non-Genesis write, so the token cannot mutate Eve.
    body = api(EVE, "/issues/39", token=token).get("body", "")
    marker, ending = "<!-- continuous-eve-ack -->", "<!-- /continuous-eve-ack -->"
    if body.count(marker) != 1 or body.count(ending) != 1:
        return "pending", ""
    section = body.split(marker, 1)[1].split(ending, 1)[0].strip()
    if not section.startswith(FENCE + "json\n") or not section.endswith(FENCE):
        return "pending", ""
    try:
        proof = json.loads(section[len(FENCE) + 5:-len(FENCE)].strip())
    except (TypeError, ValueError):
        return "pending", ""
    if not (proof.get("version") == 1 and
            type(proof.get("sequence")) is int and proof["sequence"] == sequence and
            proof.get("status") in ("completed", "failed")):
        return "pending", ""
    # A text-only acknowledgement is insufficient. Bind it to an actual
    # successful Eve turn runner on main; do not accept a forged run URL.
    import re
    run_url = proof.get("run_url")
    if not isinstance(run_url, str):
        return "rejected", "invalid_run_url"
    match = re.fullmatch(
        r"https://github[.]com/Maxhm007/Eve/actions/runs/([1-9][0-9]*)", run_url)
    if match is None:
        return "rejected", "invalid_run_url"
    run = api(EVE, "/actions/runs/" + match.group(1), token=token)
    if run.get("id") != int(match.group(1)) or run.get("name") != "Eve Continuous Evolution — Peer Turn":
        return "rejected", "run_identity_mismatch"
    if run.get("status") != "completed":
        return "pending", ""
    if run.get("head_branch") != "main":
        return "rejected", "non_main_ref"
    if run.get("event") not in ("schedule", "push", "workflow_dispatch"):
        return "rejected", "unsupported_event"
    if run.get("conclusion") != "success":
        return "rejected", "run_failed"
    return "accepted", proof


def ack_exists(sequence, token=""):
    return ack_result(sequence, token)[0] == "accepted"


def save(body, state, token):
    api(GENESIS, "/issues/{}".format(ISSUE), method="PATCH",
        payload={"body": encode(body, state)}, token=token)


def advance(state, owner, result):
    return {"version": 1, "sequence": state["sequence"] + 1,
            "owner": owner, "status": "ready", "lease_until": None,
            "last_result": str(result)[:240]}


def tick(token, now=None, work=None):
    if not token:
        raise ValueError("Local GitHub token required")
    now = now or datetime.now(timezone.utc)
    issue = api(GENESIS, "/issues/{}".format(ISSUE), token=token)
    body = issue["body"]
    state = decode(body)
    if state["owner"] == "eve":
        receipt_status, receipt = ack_result(state["sequence"], token=token)
        if receipt_status == "accepted":
            if receipt.get("status") == "failed":
                result = "eve failed #{}: {}".format(
                    state["sequence"], str(receipt.get("summary", "unspecified failure"))[:160])
            else:
                result = "eve completed #{}".format(state["sequence"])
            save(body, advance(state, "genesis", result), token)
            return tick(token, now=now, work=work)
        if receipt_status == "rejected":
            result = "eve receipt rejected: {}".format(receipt)
            save(body, advance(state, "genesis", result), token)
            # A terminal rejected receipt can be recorded and recovered in
            # this bounded tick, without waiting for the lease to expire.
            return tick(token, now=now, work=work)
        if state["status"] == "running" and deadline(state.get("lease_until"), now):
            save(body, advance(state, "genesis", "eve lease expired"), token)
            return "eve_lease_expired"
        if state["status"] == "ready":
            state["status"] = "running"
            state["lease_until"] = (now + timedelta(minutes=TIMEOUT_MINUTES)).isoformat()
            save(body, state, token)
        return "await_eve"
    if state["status"] == "running":
        if deadline(state.get("lease_until"), now):
            save(body, advance(state, "eve", "genesis lease expired"), token)
            return "genesis_lease_expired"
        return "await_genesis"
    state["status"] = "running"
    state["lease_until"] = (now + timedelta(minutes=TIMEOUT_MINUTES)).isoformat()
    save(body, state, token)
    runner = work or (lambda: subprocess.run(
        [sys.executable, "scripts/genesis_teammate.py", "autonomous",
         "--run-id", os.getenv("GITHUB_RUN_ID", "0")],
        capture_output=True, text=True, timeout=450, check=False))
    try:
        completed = runner()
        # Exit code is a completion signal, not evidence of a successful fix.
        # Retain a short diagnostic category, not raw potentially sensitive logs.
        result = "genesis teammate exit {}".format(completed.returncode)
        if completed.returncode != 0:
            output = (completed.stderr or completed.stdout or "")
            category = "traceback" if "Traceback (most recent call last)" in output else (
                "github_api" if "GitHub API" in output else "command_failed")
            result += "; category=" + category
    except subprocess.TimeoutExpired:
        result = "genesis teammate timed out"
    if state.get("last_result", "").startswith(("eve failed #", "eve receipt rejected:")):
        result = result + "; " + state["last_result"]
    save(encode(body, state), advance(state, "eve", result), token)
    return result


if __name__ == "__main__":
    print(tick(os.environ.get("GITHUB_TOKEN", "")))

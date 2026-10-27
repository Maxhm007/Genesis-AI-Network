"""Single guarded wake path for the Agentic Lab Recovery controller.

Many workflows and scripts wake ``genesis-agentic-lab-recovery.yml``. That
workflow serializes controller runs in one concurrency group with
``cancel-in-progress: false``, so GitHub keeps one running and at most one
pending run; every extra dispatch replaces (cancels) the pending one. Waking
again while a controller run is already queued/running, or right after one was
dispatched, therefore adds nothing but a cancelled run. This helper skips such
redundant wakes. It fails open: if the run list cannot be read, it dispatches.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

LAB_RECOVERY_WORKFLOW = "genesis-agentic-lab-recovery.yml"
DISPATCH_PATH = f"/actions/workflows/{LAB_RECOVERY_WORKFLOW}/dispatches"
RUNS_PATH = f"/actions/workflows/{LAB_RECOVERY_WORKFLOW}/runs?per_page=20"
ACTIVE_STATUSES = frozenset({"queued", "in_progress", "pending", "waiting", "requested"})
# push / pull_request runs use separate validation concurrency groups and do
# not perform the controller pass, so they never make a wake redundant.
NON_CONTROLLER_EVENTS = frozenset({"push", "pull_request"})
DEBOUNCE_SECONDS = 120


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def redundant_wake_reason(
    runs: Iterable[dict] | None,
    now: datetime | None = None,
    debounce_seconds: int = DEBOUNCE_SECONDS,
) -> str:
    """Return a skip reason when a new wake would be redundant, else ``""``."""
    now = now or datetime.now(timezone.utc)
    for run in runs or ():
        if not isinstance(run, dict):
            continue
        if str(run.get("event") or "") in NON_CONTROLLER_EVENTS:
            continue
        status = str(run.get("status") or "").lower()
        number = run.get("run_number") or run.get("id") or "?"
        if status in ACTIVE_STATUSES:
            return f"lab_recovery_run_{status}:#{number}"
        created = _parse_time(run.get("created_at") or run.get("createdAt"))
        if created is not None and 0 <= (now - created).total_seconds() < debounce_seconds:
            return f"lab_recovery_dispatched_recently:#{number}"
    return ""


def wake_lab_recovery(
    api: Callable[[str, str, dict | None], Any],
    now: datetime | None = None,
) -> dict:
    """Dispatch Lab Recovery through ``api(method, path, payload)`` unless redundant.

    ``api`` is the caller's own GitHub REST helper (paths relative to
    ``/repos/{owner}/{repo}``). Errors from the dispatch POST propagate so
    callers keep their existing error handling.
    """
    try:
        listing = api("GET", RUNS_PATH, None)
        runs = listing.get("workflow_runs") if isinstance(listing, dict) else None
        reason = redundant_wake_reason(runs if isinstance(runs, list) else [], now=now)
    except Exception:
        reason = ""
    if reason:
        return {"dispatched": False, "skipped": reason}
    api("POST", DISPATCH_PATH, {"ref": "main"})
    return {"dispatched": True, "skipped": ""}


def wake_lab_recovery_via_gh(repository: str, run: Callable[[list[str]], Any]) -> bool:
    """``gh`` CLI variant for scripts that shell out; ``run`` returns a CompletedProcess.

    Returns True when a wake was dispatched or was skipped as redundant.
    """
    import json

    def api(method: str, path: str, payload: dict | None) -> Any:
        if method == "GET":
            result = run(["gh", "api", f"repos/{repository}{path}"])
            if getattr(result, "returncode", 1) != 0:
                raise RuntimeError("could not list Lab Recovery runs")
            return json.loads(getattr(result, "stdout", "") or "{}")
        result = run(["gh", "workflow", "run", LAB_RECOVERY_WORKFLOW, "--repo", repository, "--ref", "main"])
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError("Lab Recovery dispatch failed")
        return None

    try:
        outcome = wake_lab_recovery(api)
    except Exception:
        return False
    if outcome.get("skipped"):
        print(f"Agentic Lab Recovery wake skipped: {outcome['skipped']}")
    return True

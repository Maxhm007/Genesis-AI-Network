from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import json

from genesis import lab_recovery_wake as wake

NOW = datetime(2026, 10, 27, 15, 30, tzinfo=timezone.utc)


def _run(status="completed", event="workflow_dispatch", seconds_ago=600, number=1):
    created = (NOW - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")
    return {"run_number": number, "status": status, "event": event, "created_at": created}


def _api(runs, calls):
    def api(method, path, payload):
        calls.append((method, path, payload))
        if method == "GET":
            return {"workflow_runs": runs}
        return None
    return api


def test_skips_when_controller_run_queued_or_running():
    for status in ("queued", "in_progress", "pending", "waiting", "requested"):
        calls = []
        result = wake.wake_lab_recovery(_api([_run(status=status)], calls), now=NOW)
        assert result["dispatched"] is False
        assert status in result["skipped"]
        assert all(method == "GET" for method, _, _ in calls)


def test_skips_when_dispatched_within_debounce_window():
    calls = []
    result = wake.wake_lab_recovery(_api([_run(seconds_ago=30)], calls), now=NOW)
    assert result["dispatched"] is False
    assert "recently" in result["skipped"]


def test_dispatches_when_idle_and_last_run_is_old():
    calls = []
    result = wake.wake_lab_recovery(_api([_run(seconds_ago=600)], calls), now=NOW)
    assert result["dispatched"] is True
    assert ("POST", wake.DISPATCH_PATH, {"ref": "main"}) in calls


def test_push_and_pull_request_validation_runs_do_not_block_wake():
    calls = []
    runs = [_run(status="in_progress", event="push"), _run(status="queued", event="pull_request", seconds_ago=5)]
    assert wake.wake_lab_recovery(_api(runs, calls), now=NOW)["dispatched"] is True


def test_fails_open_when_run_listing_errors():
    calls = []

    def api(method, path, payload):
        calls.append(method)
        if method == "GET":
            raise RuntimeError("boom")

    assert wake.wake_lab_recovery(api, now=NOW)["dispatched"] is True
    assert calls == ["GET", "POST"]


def test_gh_variant_skips_and_dispatches():
    issued = []

    def runner(runs):
        def run(args):
            issued.append(args)
            if args[:2] == ["gh", "api"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"workflow_runs": runs}))
            return SimpleNamespace(returncode=0, stdout="")
        return run

    assert wake.wake_lab_recovery_via_gh("o/r", runner([_run(status="in_progress", seconds_ago=0)])) is True
    assert not any(args[:3] == ["gh", "workflow", "run"] for args in issued)
    issued.clear()
    assert wake.wake_lab_recovery_via_gh("o/r", runner([])) is True
    assert any(args[:3] == ["gh", "workflow", "run"] for args in issued)


def test_workflow_wakes_are_guarded_and_solver_is_single_lane():
    workflows = Path(".github/workflows")
    for path in workflows.glob("*.yml"):
        text = path.read_text()
        if "gh workflow run genesis-agentic-lab-recovery.yml" in text:
            assert "gh run list" in text, f"{path.name} wakes Lab Recovery without a redundancy guard"
    lab = (workflows / "genesis-agentic-lab-recovery.yml").read_text()
    assert "cancel-in-progress: false" in lab
    assert "GENESIS_AGENTIC_MAX_PARALLEL: '1'" in lab
    worker = (workflows / "genesis-agentic-strategy-worker.yml").read_text()
    assert "'genesis-agentic-solver-single-lane'" in worker
    assert "cancel-in-progress: false" in worker

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))


def newer_successful_run(failed_run: dict[str, Any], workflow_runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    failed_created = _dt(str(failed_run.get("created_at") or ""))
    failed_id = int(failed_run.get("id") or 0)

    eligible: list[dict[str, Any]] = []
    for run in workflow_runs:
        if int(run.get("id") or 0) == failed_id:
            continue
        if str(run.get("head_branch") or "") != "main":
            continue
        if str(run.get("status") or "") != "completed":
            continue
        if str(run.get("conclusion") or "") != "success":
            continue
        created = _dt(str(run.get("created_at") or ""))
        if created <= failed_created:
            continue
        eligible.append(run)

    if not eligible:
        return None
    eligible.sort(key=lambda run: _dt(str(run.get("created_at") or "")), reverse=True)
    return eligible[0]


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Detect whether an Action failure has recovered")
    parser.add_argument("--failed-run", type=Path, required=True)
    parser.add_argument("--workflow-runs", type=Path, required=True)
    args = parser.parse_args()

    failed = json.loads(args.failed_run.read_text(encoding="utf-8"))
    payload = json.loads(args.workflow_runs.read_text(encoding="utf-8"))
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else payload
    if not isinstance(runs, list):
        raise SystemExit("workflow runs payload must contain a list")

    recovered = newer_successful_run(failed, runs)
    print(json.dumps({"recovered": bool(recovered), "run": recovered or {}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

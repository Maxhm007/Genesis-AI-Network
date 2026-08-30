from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.github_issue_terminal_reconciler import (
    _is_specialist_handoff,
    _is_specialist_replacement,
    _issue_number,
)
from genesis.modules.task_queue import PersistentTaskQueue


def inspect_pending_specialist_handoffs(root: Path) -> dict:
    """Return Issue handoffs that still lack a real specialist replacement task."""
    root = Path(root).resolve()
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    groups: dict[int, list] = {}
    for task in queue.list(limit=5000):
        issue_number = _issue_number(task)
        if issue_number > 0:
            groups.setdefault(issue_number, []).append(task)

    pending: list[dict] = []
    for issue_number, tasks in sorted(groups.items()):
        handoffs = [task for task in tasks if _is_specialist_handoff(task)]
        replacements = [task for task in tasks if _is_specialist_replacement(task)]
        if handoffs and not replacements:
            pending.append(
                {
                    "github_issue_number": issue_number,
                    "handoff_task_ids": [task.task_id for task in handoffs],
                    "reason": "awaiting_specialist_replacement",
                }
            )

    return {
        "status": "ok",
        "pending": bool(pending),
        "pending_count": len(pending),
        "handoffs": pending,
    }


def _write_output(path: Path, result: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"pending={'true' if result['pending'] else 'false'}\n")
        handle.write(f"pending_count={result['pending_count']}\n")
        issue_numbers = ",".join(str(row["github_issue_number"]) for row in result["handoffs"])
        handle.write(f"issue_numbers={issue_numbers}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--github-output", default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    result = inspect_pending_specialist_handoffs(root)
    if args.github_output:
        _write_output(Path(args.github_output), result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

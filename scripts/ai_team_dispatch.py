from __future__ import annotations

import json
from pathlib import Path

from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import ProviderRegistry
from genesis.team import AITeam


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    route_path = runtime / "task_route.json"
    report = {"status": "not_requested", "task_id": None, "outputs": []}

    if route_path.is_file():
        route = json.loads(route_path.read_text(encoding="utf-8"))
        decision = route.get("decision") or {}
        task_id = str(decision.get("task_id", ""))
        use_ai_team = bool(decision.get("use_ai_team", False))
        report["task_id"] = task_id or None
        if use_ai_team and task_id:
            queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
            task = queue.get(task_id)
            if task is not None:
                team = AITeam(ProviderRegistry())
                context = json.dumps(
                    {
                        "owner_module": task.module_id,
                        "priority": task.priority,
                        "payload": task.payload,
                    },
                    sort_keys=True,
                )
                outputs = team.run_task(task.objective, context=context)
                report = {
                    "status": "completed",
                    "task_id": task.task_id,
                    "owner_module": task.module_id,
                    "outputs": outputs,
                    "rule": "AI Team provides bounded specialist analysis. The owning module remains responsible for execution and normal Security/validation gates still apply.",
                }

    (runtime / "ai_team_dispatch.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))

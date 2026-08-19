from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from .modules.task_queue import GenesisTask, PersistentTaskQueue
from .resource import ResourceModule, ResourceSnapshot
from .task_router import TaskRouterModule


PROTECTED_PREFIXES = (
    ".github/",
    "GENESIS_CONSTITUTION.md",
    "GENESIS_BLOCK.json",
)


class GenesisCoreProcessor:
    """Central coordination kernel for Genesis.

    The processor is deliberately not an intelligence provider and has no direct
    code-promotion authority. It coordinates durable work, resource pressure,
    routing, risk lanes and operational state while specialist modules/Genes do
    the reasoning and execution.
    """

    MODULE_ID = "genesis.core_processor"
    MIN_CAPACITY_SCORE = 20.0

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.router = TaskRouterModule(self.root)
        self.resources = ResourceModule()
        self.status_path = self.runtime / "core_processor.json"

    def _state_summary(self) -> dict:
        tasks = self.queue.list(limit=500)
        states = Counter(task.state for task in tasks)
        modules = Counter((task.module_id or "unassigned") for task in tasks if task.state not in {"complete", "cancelled"})
        failures = Counter(
            str(row.get("classification") or "unknown")
            for task in tasks
            for row in task.failure_history[-1:]
        )
        return {
            "total_tasks": len(tasks),
            "states": dict(sorted(states.items())),
            "pending_modules": dict(sorted(modules.items())),
            "latest_failure_classes": dict(sorted(failures.items())),
        }

    @staticmethod
    def _dispatch_lane(task: GenesisTask | None) -> str:
        if task is None:
            return "none"
        target = str(task.payload.get("target_path") or "").replace("\\", "/").lstrip("./")
        if any(target == prefix or target.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            return "privileged"
        text = f"{task.objective}\n{json.dumps(task.payload, sort_keys=True)}".lower()
        if any(marker in text for marker in ("constitution", "genesis block", "root trust", "validator quorum", "workflow security")):
            return "privileged"
        return "normal"

    def _resource_policy(self, snapshot: ResourceSnapshot | None) -> dict:
        if snapshot is None:
            return {"mode": "unmeasured", "capacity_score": None, "dispatch_allowed": True}
        score = self.resources.capacity_score(snapshot)
        return {
            "mode": "normal" if score >= self.MIN_CAPACITY_SCORE else "throttled",
            "capacity_score": score,
            "dispatch_allowed": score >= self.MIN_CAPACITY_SCORE,
            "snapshot": snapshot.as_dict(),
        }

    def cycle(self, resource_snapshot: ResourceSnapshot | None = None) -> dict:
        """Run one central scheduling/coordination cycle.

        This does not execute the assigned task. It decides whether scheduling is
        permitted, delegates assignment to the durable task router, records the
        risk lane and publishes one system-level state snapshot for downstream
        Genes/modules.
        """
        before = self._state_summary()
        resource = self._resource_policy(resource_snapshot)
        if resource["dispatch_allowed"]:
            routing = self.router.assign_next()
        else:
            routing = {
                "status": "resource_throttled",
                "decision": None,
                "reason": "central resource capacity below safe dispatch threshold",
            }

        selected_task = None
        decision = routing.get("decision") if isinstance(routing, dict) else None
        if isinstance(decision, dict) and decision.get("task_id"):
            selected_task = self.queue.get(str(decision["task_id"]))

        result = {
            "processor": self.MODULE_ID,
            "role": "coordination_kernel",
            "authority": {
                "intelligence_provider": False,
                "direct_code_promotion": False,
                "validation_authority": False,
                "constitution_write": False,
            },
            "resource": resource,
            "routing": routing,
            "dispatch": {
                "task_id": selected_task.task_id if selected_task else None,
                "module_id": selected_task.module_id if selected_task else None,
                "lane": self._dispatch_lane(selected_task),
                "ai_team_requested": bool(isinstance(decision, dict) and decision.get("use_ai_team")),
            },
            "system_state_before": before,
            "system_state_after": self._state_summary(),
            "principle": "Core Processor coordinates; Genes and specialist modules provide intelligence and execution; Security and validators retain independent authority.",
        }
        self.status_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

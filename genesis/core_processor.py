from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from .gene_compute import GeneComputeFabric
from .gene_lifecycle import GeneLifecycleManager, GeneNeedEvidence
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
    routing, Gene selection, risk lanes and operational state while specialist
    modules/Genes do the reasoning and execution.
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
        self.gene_fabric = GeneComputeFabric(self.root)
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

    def evaluate_gene_lifecycle(self, evidence: GeneNeedEvidence, *, now: float | None = None) -> dict:
        """Allow Gene 0 to perform one bounded, issue-enabled lifecycle decision."""
        registry_path = self.root / "GENE_REGISTRY.json"
        if not registry_path.is_file():
            return {"status": "registry_unavailable", "created": False}
        manager = GeneLifecycleManager(
            registry_path,
            state_path=self.runtime / "gene_lifecycle_state.json",
        )
        return manager.evaluate_and_create(evidence, authority="Gene 0", now=now)

    def cycle(self, resource_snapshot: ResourceSnapshot | None = None) -> dict:
        """Run one central scheduling/coordination cycle.

        The processor decides whether scheduling is permitted, delegates durable
        task assignment, selects the best configured Gene worker for the task,
        records the risk lane and publishes one system-level snapshot. It does not
        grant a Gene validation or promotion authority.
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

        worker = None
        if selected_task is not None:
            worker = self.gene_fabric.select(selected_task.module_id, selected_task.objective)

        result = {
            "processor": self.MODULE_ID,
            "role": "coordination_kernel",
            "coordinator": self.gene_fabric.coordinator,
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
                "target_gene": worker.gene if worker else None,
                "target_gene_id": worker.logical_id if worker else None,
                "target_repository": worker.repository if worker else None,
                "model": worker.model if worker else None,
                "model_license": worker.license if worker else None,
                "worker_role": worker.role if worker else None,
            },
            "gene_topology": self.gene_fabric.topology(),
            "system_state_before": before,
            "system_state_after": self._state_summary(),
            "principle": "Gene 0 coordinates; Gene workers provide model-backed intelligence; Security and validators retain independent authority.",
        }
        self.status_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

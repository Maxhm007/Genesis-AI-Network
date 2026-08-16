from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .coding import CodingModule
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .security import SecurityModule


ENGINEERING_MODULES = {
    "genesis.security",
    "genesis.coding",
    "genesis.self_development",
    "genesis.ai_score",
}


class AutonomousEngineeringLoop:
    """Bounded bridge from security/competitive gaps to coding candidates.

    This loop may select one persistent engineering task, ask the Coding Module
    for one bounded patch, and run Security review on the produced candidate.
    It never promotes code. Independent validators remain mandatory.
    """

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        self.security = SecurityModule(self.root)
        self.coding = CodingModule(self.root, self.providers)

    def _record_security_tasks(self, report: dict) -> list[str]:
        created: list[str] = []
        for finding in report.get("findings", []):
            severity = str(finding.get("severity", "")).lower()
            if severity not in {"medium", "high", "critical"}:
                continue
            key = f"security:{finding.get('finding_id')}:{finding.get('evidence')}"
            task, was_created = self.queue.create_unique(
                key,
                f"Remediate Genesis security finding: {finding.get('title')}. {finding.get('remediation')}",
                module_id="genesis.security",
                priority={"medium": 80, "high": 95, "critical": 100}[severity],
                payload={"finding": finding, "source": "autonomous_security_scan"},
            )
            if was_created:
                created.append(task.task_id)
        return created

    def _select_task(self):
        for state in ("new", "blocked"):
            for task in self.queue.list(state=state, limit=50):
                if task.module_id in ENGINEERING_MODULES:
                    return task
        return None

    def run_once(self) -> dict:
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        security_report = self.security.write_report(runtime / "security_report.json")
        created_security_tasks = self._record_security_tasks(security_report)
        task = self._select_task()
        result = {
            "security": security_report,
            "created_security_tasks": created_security_tasks,
            "selected_task": asdict(task) if task else None,
            "coding_status": "idle",
            "candidate": None,
            "candidate_security": None,
        }
        if task is None:
            (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            return result

        try:
            if task.state == "new":
                self.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
            elif task.state == "blocked":
                self.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
            self.queue.transition(task.task_id, "running", module_id="genesis.coding")

            context_paths = list(task.payload.get("context_paths", []) or [])
            proposal = self.coding.propose(task.objective, context_paths=context_paths)
            candidate = self.coding.execute_candidate(proposal)
            result["coding_status"] = "candidate_created" if candidate.committed else "candidate_not_committed"
            result["candidate"] = asdict(candidate)
            if candidate.committed:
                candidate_security = self.security.write_report(
                    runtime / "candidate_security_report.json", candidate=True, base_ref="main"
                )
                result["candidate_security"] = candidate_security
                if candidate_security["status"] != "pass":
                    result["coding_status"] = "candidate_rejected_by_security"
                self.queue.transition(task.task_id, "review", module_id="genesis.coding")
            else:
                self.queue.transition(task.task_id, "blocked", module_id="genesis.coding")
        except Exception as exc:
            result["coding_status"] = "provider_or_candidate_error"
            result["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            current = self.queue.get(task.task_id)
            if current and current.state in {"assigned", "running"}:
                try:
                    self.queue.transition(task.task_id, "blocked", module_id="genesis.coding")
                except Exception:
                    pass

        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

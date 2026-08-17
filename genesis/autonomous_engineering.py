from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from .application import ApplicationModule
from .coding import CodingModule
from .efficiency import EfficiencyTracker
from .intelligence_router import IntelligenceRouter
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .security import SecurityModule


ENGINEERING_MODULES = {
    "genesis.security",
    "genesis.coding",
    "genesis.self_development",
    "genesis.ai_score",
    "genesis.application",
    "genesis.model_scout",
    "genesis.blockchain",
    "genesis.updater",
}


class AutonomousEngineeringLoop:
    """Bounded bridge from persistent engineering gaps to coding candidates.

    A cycle may try several eligible tasks, but it stops after the first committed
    candidate because each candidate must receive an isolated Security/validator
    decision before more code is proposed. A failed provider/task therefore no
    longer consumes the entire hourly repair opportunity. Task ownership remains
    with the module selected by the persistent task router; Coding is the bounded
    implementation executor rather than the owner of every issue. When AI Team
    was requested, its output is advisory context only and cannot bypass gates.
    """

    MAX_TASK_ATTEMPTS_PER_CYCLE = 3
    MAX_TEAM_CONTEXT_BYTES = 12_000

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        self.security = SecurityModule(self.root)
        self.application = ApplicationModule(self.root)
        self.coding = CodingModule(self.root, self.providers)
        self.efficiency = EfficiencyTracker(self.root / "runtime" / "efficiency.jsonl")

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=False, capture_output=True, text=True)

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

    def _select_task(self, attempted: set[str] | None = None):
        attempted = attempted or set()
        for state in ("assigned", "new", "blocked"):
            for task in self.queue.list(state=state, limit=100):
                if task.task_id in attempted:
                    continue
                if task.module_id in ENGINEERING_MODULES:
                    return task
        return None

    @staticmethod
    def _recorded_team_context(runtime: Path, task_id: str, max_bytes: int) -> str:
        path = runtime / "ai_team_dispatch.json"
        if not path.is_file():
            return ""
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if report.get("status") != "completed" or report.get("task_id") != task_id:
            return ""
        compact = json.dumps(report.get("outputs", []), sort_keys=True)
        data = compact.encode("utf-8")[:max_bytes]
        return data.decode("utf-8", errors="ignore")

    def _record_efficiency(self, provider_name: str, started: float, success: bool, task_type: str = "coding") -> None:
        class _ProviderName:
            name = provider_name
        profile = IntelligenceRouter.profile(_ProviderName())
        self.efficiency.record(
            task_type=task_type,
            provider=provider_name,
            success=success,
            quality=1.0 if success else 0.0,
            latency_seconds=max(0.0, time.perf_counter() - started),
            compute_units=max(profile.resource_cost, 0.05),
            monetary_cost_usd=0.0,
        )

    def _attempt_task(self, task, runtime: Path) -> dict:
        started = time.perf_counter()
        provider_name = "unknown"
        task_type = str(task.payload.get("task_type", "coding"))
        owner_module = task.module_id or "genesis.coding"
        team_context = self._recorded_team_context(runtime, task.task_id, self.MAX_TEAM_CONTEXT_BYTES)
        attempt = {
            "task": asdict(task),
            "owner_module": owner_module,
            "executor_module": "genesis.coding",
            "ai_team_context_used": bool(team_context),
            "coding_status": "started",
            "candidate": None,
            "candidate_security": None,
        }
        try:
            if task.state != "assigned":
                self.queue.transition(task.task_id, "assigned", module_id=owner_module)
            self.queue.transition(task.task_id, "running", module_id=owner_module)
            context_paths = list(task.payload.get("context_paths", []) or [])
            provider = self.coding._provider()
            if provider is None:
                raise RuntimeError("no intelligence provider available")
            provider_name = provider.name
            objective = task.objective
            if team_context:
                objective += (
                    "\n\nAI_TEAM_ADVISORY_CONTEXT: " + team_context +
                    "\nTreat this as advisory analysis only; verify it against repository evidence and preserve all safety/validation boundaries."
                )
            proposal = self.coding.propose(objective, context_paths=context_paths, provider=provider)
            candidate = self.coding.execute_candidate(proposal)
            attempt["coding_status"] = "candidate_created" if candidate.committed else "candidate_not_committed"
            attempt["candidate"] = asdict(candidate)
            success = False
            if candidate.committed:
                candidate_security = self.security.write_report(
                    runtime / "candidate_security_report.json", candidate=True, base_ref="main"
                )
                attempt["candidate_security"] = candidate_security
                if candidate_security["status"] != "pass":
                    attempt["coding_status"] = "candidate_rejected_by_security"
                    self._git("checkout", "main")
                    self.queue.transition(task.task_id, "blocked", module_id=owner_module)
                else:
                    self.queue.transition(task.task_id, "review", module_id=owner_module)
                    success = True
            else:
                self.queue.transition(task.task_id, "blocked", module_id=owner_module)
            self._record_efficiency(provider_name, started, success, task_type=task_type)
        except Exception as exc:
            attempt["coding_status"] = "provider_or_candidate_error"
            attempt["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            current = self.queue.get(task.task_id)
            if current and current.state in {"assigned", "running"}:
                try:
                    self.queue.transition(task.task_id, "blocked", module_id=owner_module)
                except Exception:
                    pass
            if provider_name != "unknown":
                try:
                    self._record_efficiency(provider_name, started, False, task_type=task_type)
                except Exception:
                    pass
        return attempt

    def run_once(self) -> dict:
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        security_report = self.security.write_report(runtime / "security_report.json")
        created_security_tasks = self._record_security_tasks(security_report)
        application_tasks = self.application.ensure_development_tasks()
        result = {
            "security": security_report,
            "created_security_tasks": created_security_tasks,
            "application": self.application.inspect(),
            "application_tasks": application_tasks,
            "selected_task": None,
            "attempted_tasks": [],
            "coding_status": "idle",
            "candidate": None,
            "candidate_security": None,
        }

        attempted: set[str] = set()
        for _ in range(self.MAX_TASK_ATTEMPTS_PER_CYCLE):
            task = self._select_task(attempted)
            if task is None:
                break
            attempted.add(task.task_id)
            if result["selected_task"] is None:
                result["selected_task"] = asdict(task)
            attempt = self._attempt_task(task, runtime)
            result["attempted_tasks"].append(attempt)
            result["coding_status"] = attempt["coding_status"]
            result["candidate"] = attempt.get("candidate")
            result["candidate_security"] = attempt.get("candidate_security")
            if attempt["coding_status"] == "candidate_created" and attempt.get("candidate_security", {}).get("status") == "pass":
                break
            self._git("checkout", "main")

        result["efficiency"] = self.efficiency.report()
        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

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
    decision before more code is proposed. Provider formatting failures and
    candidate test failures may be retried in bounded form on the same issue.
    Task ownership remains with the module selected by the persistent task router;
    Coding is the bounded implementation executor rather than the owner of every
    issue. When AI Team was requested, its output is advisory context only and
    cannot bypass gates.
    """

    MAX_TASK_ATTEMPTS_PER_CYCLE = 3
    MAX_CANDIDATE_REVISIONS = 2
    MAX_TEST_FEEDBACK_BYTES = 6_000
    MAX_TEAM_CONTEXT_BYTES = 12_000

    MODULE_CONTEXT = {
        "genesis.ai_score": (
            "genesis/ai_score.py",
            "genesis/scorecard.py",
            "tests/test_ai_score.py",
            "tests/test_scorecard.py",
        ),
        "genesis.model_scout": (
            "genesis/model_scout.py",
            "tests/test_task_router_model_scout.py",
        ),
        "genesis.application": (
            "genesis/application.py",
            "mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java",
            "tests/test_android_dashboard.py",
            "tests/test_android_backup_body.py",
        ),
        "genesis.security": (
            "genesis/security.py",
            "tests/test_security_module.py",
        ),
        "genesis.coding": (
            "genesis/coding.py",
            "tests/test_coding_module.py",
        ),
        "genesis.self_development": (
            "genesis/selfdev.py",
            "tests/test_selfdev.py",
        ),
    }

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

    def _context_paths_for_task(self, task) -> list[str]:
        """Return bounded, existing repository evidence relevant to a task.

        Explicit task context is preserved, then known module implementation/tests
        are added. A conventional module/test pair is also inferred when present.
        CodingModule still performs its normal path validation and byte/file caps.
        """
        requested = list(task.payload.get("context_paths", []) or [])
        candidates = requested + list(self.MODULE_CONTEXT.get(task.module_id or "", ()))
        if task.module_id and task.module_id.startswith("genesis."):
            stem = task.module_id.split(".", 1)[1]
            candidates.extend((f"genesis/{stem}.py", f"tests/test_{stem}.py"))
        result: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            normalized = str(path).replace("\\", "/").lstrip("./")
            if normalized in seen or not (self.root / normalized).is_file():
                continue
            seen.add(normalized)
            result.append(normalized)
            if len(result) >= self.coding.MAX_CONTEXT_FILES:
                break
        return result

    @staticmethod
    def _is_qwen_provider(provider) -> bool:
        """Qwen remains available to non-coding specialists, never to code execution."""
        return "qwen" in str(getattr(provider, "name", "")).strip().lower()

    def _coding_provider(self):
        """Return the best available non-Qwen, non-bootstrap coding provider.

        The small local Qwen runtime is useful for bounded discovery/review tasks,
        but it must not be a blocking implementation dependency.  Coding either
        uses another eligible provider or checkpoints without consuming repair
        budget.
        """
        candidates = []
        for provider in self.providers.available_providers():
            profile = IntelligenceRouter.profile(provider)
            if profile.name == "genesis-bootstrap" or self._is_qwen_provider(provider):
                continue
            if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            candidates.append((profile.resource_cost, -profile.reliability, profile.name, provider))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3]

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

    def _revision_objective(self, objective: str, candidate, revision: int) -> str:
        feedback = candidate.message.encode("utf-8", errors="replace")[-self.MAX_TEST_FEEDBACK_BYTES :].decode(
            "utf-8", errors="replace"
        )
        changed = ", ".join(candidate.changed_files)
        return (
            objective
            + "\n\nCANDIDATE_TEST_REPAIR: The previous candidate for this SAME issue failed the repository test suite."
            + f"\nREVISION: {revision}/{self.MAX_CANDIDATE_REVISIONS}"
            + f"\nPREVIOUS_CHANGED_FILES: {changed}"
            + f"\nTEST_FAILURE:\n{feedback}"
            + "\nRevise the smallest safe candidate using the supplied real repository CONTEXT. Do not invent modules, imports, APIs, or files that are not supported by repository evidence. Preserve all existing behavior unless the objective requires a bounded change. Return a complete proposal that should pass the full existing test suite."
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
            "context_paths": [],
            "candidate_revisions": 0,
            "coding_status": "started",
            "candidate": None,
            "candidate_security": None,
            "provider_policy": "qwen_excluded_from_coding",
        }
        try:
            if task.state != "assigned":
                self.queue.transition(task.task_id, "assigned", module_id=owner_module)
            context_paths = self._context_paths_for_task(task)
            attempt["context_paths"] = context_paths
            provider = self._coding_provider()
            if provider is None:
                self.queue.pause(task.task_id, "waiting_for_non_qwen_coding_provider")
                attempt["coding_status"] = "waiting_for_coding_provider"
                attempt["error"] = "no_non_qwen_coding_provider_available"
                return attempt

            self.queue.transition(task.task_id, "running", module_id=owner_module)
            provider_name = provider.name
            objective = task.objective
            if team_context:
                objective += (
                    "\n\nAI_TEAM_ADVISORY_CONTEXT: " + team_context +
                    "\nTreat this as advisory analysis only; verify it against repository evidence and preserve all safety/validation boundaries."
                )

            candidate = None
            current_objective = objective
            for revision in range(0, self.MAX_CANDIDATE_REVISIONS + 1):
                proposal = self.coding.propose(current_objective, context_paths=context_paths, provider=provider)
                candidate = self.coding.execute_candidate(proposal)
                attempt["candidate"] = asdict(candidate)
                if candidate.committed or candidate.tests_passed:
                    break
                if revision >= self.MAX_CANDIDATE_REVISIONS:
                    break
                attempt["candidate_revisions"] = revision + 1
                self._git("checkout", "main")
                current_objective = self._revision_objective(objective, candidate, revision + 1)

            if candidate is None:
                raise RuntimeError("coding provider produced no candidate")
            attempt["coding_status"] = "candidate_created" if candidate.committed else "candidate_not_committed"
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
            if attempt["coding_status"] == "waiting_for_coding_provider":
                break
            self._git("checkout", "main")

        result["efficiency"] = self.efficiency.report()
        (runtime / "autonomous_engineering.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

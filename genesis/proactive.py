from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ai_score import GenesisAIScorer
from .capabilities import CapabilityEvaluator
from .modules.runtime import ModularGenesis
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .selfdev import SelfDevelopmentExecutor, SelfDevResult
from .team import AITeam


@dataclass(frozen=True)
class DevelopmentPlan:
    title: str
    rationale: str
    proposal: dict


class ProactiveDevelopmentLoop:
    """Choose and execute one bounded improvement at a time.

    A low competitive AI score must create persistent improvement work. Code
    changes still require bounded candidate generation and independent validation.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.executor = SelfDevelopmentExecutor(self.root)
        self.providers = ProviderRegistry()
        self.team = AITeam(self.providers)
        self.tasks = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    def capability_report(self) -> dict:
        return CapabilityEvaluator(self.root, self.providers, self.team).report()

    def ai_score_report(self) -> dict:
        return GenesisAIScorer(self.root, self.providers, self.team).report()

    def ensure_score_work(self) -> dict | None:
        score = self.ai_score_report()
        if score["score"] >= 99 or not score.get("priority_gaps"):
            return None
        gap = score["priority_gaps"][0]
        key = f"competitive-ai:{score.get('reference_as_of')}:{gap['name']}"
        task, created = self.tasks.create_unique(
            key,
            f"Raise Genesis competitive AI score by improving or measuring the weakest dimension: {gap['name']}",
            module_id="genesis.capability",
            priority=100 if score["score"] < 55 else 90,
            payload={
                "task_type": "competitive_ai_improvement",
                "competitive_score": score["score"],
                "reference_as_of": score.get("reference_as_of"),
                "dimension": gap,
                "required_outcome": "Produce evidence, benchmark work, provider scouting, or a bounded candidate improvement; do not self-award score.",
            },
        )
        return {"task_id": task.task_id, "created": created, "dimension": gap["name"], "priority": task.priority}

    def _scan_summary(self) -> dict:
        path = self.root / "runtime" / "immortality_scan.json"
        if not path.exists():
            return {"fresh": False, "priority_count": 0, "top_items": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return {
                "fresh": True,
                "created_at": payload.get("created_at"),
                "priority_count": len(payload.get("priority_items", [])),
                "top_items": payload.get("priority_items", [])[:3],
            }
        except Exception:
            return {"fresh": False, "priority_count": 0, "top_items": []}

    def inspect(self) -> list[dict]:
        self.ensure_score_work()
        score = self.ai_score_report()
        checks = [
            {
                "capability": "genesis_competitive_ai_score",
                "present": score["score"] >= 90,
                "priority": 115 if score["score"] < 55 else 108,
                "score": score["score"],
                "max_score": score["max_score"],
                "percent": score["percent"],
                "status": score["urgency"],
                "reference_as_of": score.get("reference_as_of"),
                "improvement_hint": score["priority_gaps"][0]["improvement_hint"] if score["priority_gaps"] else None,
            },
            {"capability": "runtime_health_snapshot", "present": (self.root / "genesis" / "health.py").exists(), "priority": 100},
            {"capability": "bounded_cycle_budget", "present": (self.root / "genesis" / "budget.py").exists(), "priority": 90},
            {"capability": "communication_bridge", "present": (self.root / "genesis" / "communication.py").exists(), "priority": 95},
            {"capability": "capability_measurement", "present": (self.root / "genesis" / "capabilities.py").exists(), "priority": 95},
            {"capability": "modular_intelligence_architecture", "present": (self.root / "config" / "modules.json").exists(), "priority": 95},
            {"capability": "immortality_relevance_scan", "present": self._scan_summary()["fresh"], "priority": 92, "scan": self._scan_summary()},
        ]
        report = self.capability_report()
        for result in report["results"]:
            checks.append({
                "capability": "measured:" + result["capability"],
                "present": result["score"] == result["max_score"],
                "priority": 80 if result["status"] in {"missing", "failing"} else 60,
                "score": result["score"],
                "max_score": result["max_score"],
                "status": result["status"],
                "improvement_hint": result["improvement_hint"],
            })
        return sorted(checks, key=lambda item: item["priority"], reverse=True)

    def _module_evolution_plan(self) -> DevelopmentPlan | None:
        config_path = self.root / "config" / "modules.json"
        if not config_path.exists():
            return None
        modular = ModularGenesis(self.root, self.providers)
        status = modular.status()
        proposals = status.get("module_change_proposals", [])
        if not proposals:
            return None
        structural = next((item for item in proposals if item.get("action") == "add"), None)
        if structural is None:
            return None
        candidate = dict(structural.get("candidate_manifest", {}))
        if not candidate:
            return None
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        modules = list(payload.get("modules", []))
        module_id = candidate.get("module_id")
        if not module_id or any(item.get("module_id") == module_id for item in modules):
            return None
        candidate["status"] = "active"
        metadata = dict(candidate.get("metadata", {}))
        metadata["activation_requires_candidate_promotion"] = True
        candidate["metadata"] = metadata
        modules.append(candidate)
        payload["modules"] = modules
        proposal = {"title": structural.get("title", "Add Genesis specialist module"), "files": {"config/modules.json": json.dumps(payload, indent=2, sort_keys=False) + "\n"}}
        return DevelopmentPlan(
            title=proposal["title"],
            rationale=structural.get("rationale", "Measured capability gap requires a specialist module.") + " The module is activated only if the candidate passes independent validator quorum.",
            proposal=proposal,
        )

    def plan_next(self) -> DevelopmentPlan | None:
        self.ensure_score_work()
        proposal = self.executor.next_builtin_improvement()
        title = str(proposal.get("title", ""))
        if title != "Record self-development idle state":
            primary_files = list(dict(proposal.get("files", {})))
            if primary_files and not (self.root / primary_files[0]).exists():
                measured_gaps = self.ai_score_report()["priority_gaps"][:3]
                return DevelopmentPlan(
                    title=title or "Genesis bounded improvement",
                    rationale="Genesis detected an executable bounded runtime improvement. Competitive AI pressure is " + self.ai_score_report()["urgency"] + ". Priority dimensions: " + ", ".join(item["name"] for item in measured_gaps),
                    proposal=proposal,
                )
        return self._module_evolution_plan()

    def develop_once(self) -> tuple[DevelopmentPlan | None, SelfDevResult | None]:
        plan = self.plan_next()
        if plan is None:
            return None, None
        result = self.executor.execute(plan.proposal)
        return plan, result

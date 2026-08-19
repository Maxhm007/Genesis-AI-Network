from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .ai_score import GenesisAIScorer
from .efficiency import EfficiencyTracker
from .modules.task_queue import PersistentTaskQueue
from .providers import ProviderRegistry
from .self_evaluation import GenesisSelfEvaluation
from .self_learning import SelfLearningStore


class GenesisScorecard:
    """Expose distinct capability, efficiency, mission-research and self-development evidence."""

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = Path(root).resolve()
        self.providers = providers or ProviderRegistry()

    def _immortality_progress(self) -> dict:
        runtime = self.root / "runtime"
        scan = runtime / "immortality_scan.json"
        task_dir = runtime / "task_reviews"
        queue = PersistentTaskQueue(runtime / "genesis_tasks.sqlite3")
        lessons = SelfLearningStore(runtime / "self_learning.sqlite3")

        fresh_scan = False
        if scan.exists():
            try:
                payload = json.loads(scan.read_text(encoding="utf-8"))
                stamp = datetime.fromisoformat(str(payload.get("created_at", "")).replace("Z", "+00:00"))
                fresh_scan = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() <= 24 * 3600
            except Exception:
                fresh_scan = False

        research_tasks = [task for task in queue.list(limit=1000) if task.payload.get("task_type") == "immortality_research"]
        reviews = list(task_dir.glob("*.json")) if task_dir.exists() else []
        validated_research_lessons = [
            item for item in lessons.list(state="validated", limit=1000) if item.source_type == "research_review"
        ]

        discovery_credit = 25 if fresh_scan else 0
        task_credit = min(25, len(research_tasks) * 5)
        review_credit = min(25, len(reviews) * 5)
        validation_credit = min(25, len(validated_research_lessons) * 5)
        score = discovery_credit + task_credit + review_credit + validation_credit
        return {
            "score": score,
            "max_score": 100,
            "fresh_scan_24h": fresh_scan,
            "research_tasks": len(research_tasks),
            "candidate_reviews": len(reviews),
            "validated_research_lessons": len(validated_research_lessons),
            "interpretation": "Evidence-pipeline maturity for immortality research; not a percentage of physical immortality achieved.",
        }

    def report(self) -> dict:
        ai = GenesisAIScorer(self.root, self.providers).report()
        efficiency = EfficiencyTracker(self.root / "runtime" / "efficiency.jsonl").report()
        mission = self._immortality_progress()
        self_development = GenesisSelfEvaluation(self.root).report()
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ai_capability_score": {
                "score": ai["score"],
                "max_score": ai["max_score"],
                "urgency": ai["urgency"],
                "interpretation": ai["interpretation"],
            },
            "efficiency_score": efficiency,
            "self_development_evaluation": self_development,
            "immortality_research_progress_score": mission,
            "rule": "Scores are separate. Self-development history is evidence, not permission to self-award capability or benchmark credit.",
        }

    def write(self, path: Path) -> dict:
        report = self.report()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self_eval_path = path.parent / "self_evaluation.json"
        self_eval_path.write_text(json.dumps(report["self_development_evaluation"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

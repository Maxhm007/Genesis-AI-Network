from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROUTING_VERSION = "genesis-capability-evolution-controller-v1"
ACTIVE_TASK_STATES = {"new", "assigned", "running", "paused", "blocked", "review", "failed"}
TERMINAL_GROWTH_STATES = {"complete", "quarantined", "cancelled"}


FAMILY_POLICY: dict[str, dict[str, Any]] = {
    "professional_agentic_work": {
        "target_path": "genesis/autonomous_engineering.py",
        "capability_key": "professional_agentic_work",
        "domains": ["agent_reasoning", "reliability_evaluation"],
        "needs": [
            "long-horizon task decomposition",
            "tool selection and sequencing",
            "self-correction from execution evidence",
        ],
    },
    "software_engineering": {
        "target_path": "genesis/coding.py",
        "capability_key": "software_engineering",
        "domains": ["coding_engineering", "reliability_evaluation"],
        "needs": [
            "repository-level reasoning",
            "test-grounded patch generation",
            "failure-aware code repair",
        ],
    },
    "long_horizon_tool_coding": {
        "target_path": "genesis/autonomous_engineering.py",
        "capability_key": "long_horizon_tool_coding",
        "domains": ["agent_reasoning", "coding_engineering"],
        "needs": [
            "persistent multi-step tool planning",
            "checkpointed execution and recovery",
            "verified command-result feedback loops",
        ],
    },
    "coding_agents": {
        "target_path": "genesis/coding.py",
        "capability_key": "coding_agents",
        "domains": ["coding_engineering", "agent_reasoning"],
        "needs": [
            "repository navigation",
            "implementation planning",
            "test and review feedback integration",
        ],
    },
    "general_frontier_intelligence": {
        "target_path": "genesis/adaptive_learning.py",
        "capability_key": "general_frontier_intelligence",
        "domains": ["agent_reasoning", "memory_learning", "reliability_evaluation"],
        "needs": [
            "multi-step reasoning",
            "retrieval and durable learning",
            "uncertainty-aware self-correction",
        ],
    },
    "genomics_scientific_reasoning": {
        "target_path": "genesis/research.py",
        "capability_key": "genomics_scientific_reasoning",
        "domains": ["agent_reasoning", "memory_learning", "reliability_evaluation"],
        "needs": [
            "scientific evidence synthesis",
            "structured hypothesis evaluation",
            "provenance-aware biological reasoning",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stable_key(*parts: object) -> str:
    raw = "\n".join(str(part or "").strip() for part in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _safe_error(value: object, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"\b[0-9a-f]{24,}\b", "<id>", text, flags=re.IGNORECASE)
    return text[:limit]


def _normalized_failure(value: object) -> str:
    text = _safe_error(value, 240).lower()
    text = re.sub(r"\b\d+\b", "#", text)
    text = re.sub(r"\s+", " ", text)
    return text[:180]


class CapabilityEvolutionController:
    """Turn measured benchmark deficits into validated capability-growth work.

    This controller separates three facts that must never be conflated:
    1. an unmeasured benchmark means Genesis lacks evidence, not necessarily ability;
    2. a validated below-reference measurement is a real capability gap;
    3. a promoted code change is not an improvement until a post-promotion benchmark
       measurement demonstrates a gain.

    It reuses the existing task queue, autonomy pipeline, benchmark evidence rules,
    review, independent validation, and promotion path. It never self-awards score.
    """

    STATUS_FILE = "status.json"
    EVENTS_FILE = "events.jsonl"
    LEARNED_TARGET = "genesis/learned_capabilities.py"
    LEARNED_MARKER = "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT"

    def __init__(self, root: Path, *, queue=None, pipeline=None) -> None:
        from .autonomy_pipeline import PipelineStore
        from .modules.task_queue import PersistentTaskQueue

        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime" / "capability_evolution"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = queue or PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")
        self.pipeline = pipeline or PipelineStore(self.queue.path)
        self.status_path = self.runtime / self.STATUS_FILE
        self.events_path = self.runtime / self.EVENTS_FILE

    def _reference(self) -> dict[str, Any]:
        runtime = self.root / "runtime" / "competitive_ai_reference.json"
        config = self.root / "config" / "competitive_ai_reference.json"
        path = runtime if runtime.is_file() else config
        if not path.is_file():
            return {"as_of": None, "benchmarks": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"as_of": None, "benchmarks": []}

    def _results(self) -> dict[str, Any]:
        path = self.root / "runtime" / "competitive_benchmark_results.json"
        if not path.is_file():
            return {"benchmarks": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"benchmarks": {}}

    @staticmethod
    def _validated(result: object) -> bool:
        from .competitive_benchmarks import CompetitiveBenchmarkPlanner

        return CompetitiveBenchmarkPlanner.is_validated_measurement(result)

    @staticmethod
    def _policy(family: str) -> dict[str, Any]:
        policy = dict(FAMILY_POLICY.get(family, {}))
        if not policy:
            policy = {
                "target_path": "genesis/adaptive_learning.py",
                "capability_key": re.sub(r"[^a-z0-9_]+", "_", family.lower()).strip("_") or "frontier_capability",
                "domains": ["agent_reasoning", "reliability_evaluation"],
                "needs": ["measurable reasoning improvement", "evidence-driven self-correction"],
            }
        return policy

    def benchmark_gaps(self) -> list[dict[str, Any]]:
        reference = self._reference()
        results = self._results().get("benchmarks", {})
        gaps: list[dict[str, Any]] = []
        for benchmark in reference.get("benchmarks", []):
            benchmark_id = str(benchmark.get("id") or "").strip()
            if not benchmark_id:
                continue
            family = str(benchmark.get("family") or benchmark_id).strip()
            target = float(benchmark.get("reference_score") or 0.0)
            weight = int(benchmark.get("weight") or 0)
            result = results.get(benchmark_id)
            validated = self._validated(result)
            actual = float(result["score"]) if validated else None
            ratio = None if actual is None or target <= 0 else max(0.0, actual / target)
            if validated and target > 0 and actual >= target:
                status = "at_or_above_reference"
                shortfall = 0.0
            elif validated:
                status = "measured_below_reference"
                shortfall = max(0.0, 1.0 - float(ratio or 0.0))
            else:
                status = "unmeasured"
                shortfall = 1.0
            policy = self._policy(family)
            evidence = (
                f"Validated benchmark {benchmark_id}={actual:g}/{target:g} {benchmark.get('unit', 'score')}"
                if actual is not None
                else f"Benchmark {benchmark_id} is unmeasured against reference {target:g} {benchmark.get('unit', 'score')}"
            )
            gaps.append(
                {
                    "gap_key": _stable_key("benchmark_gap", benchmark_id),
                    "benchmark_id": benchmark_id,
                    "family": family,
                    "status": status,
                    "actual_score": actual,
                    "reference_score": target,
                    "ratio_to_reference": round(ratio, 6) if ratio is not None else None,
                    "shortfall": round(shortfall, 6),
                    "weight": weight,
                    "unit": str(benchmark.get("unit") or "score"),
                    "reference_as_of": reference.get("as_of"),
                    "measurement_status": str(result.get("status") or "") if isinstance(result, dict) else None,
                    "measured_at": (
                        str((result.get("provenance") or {}).get("measured_at") or "")
                        if isinstance(result, dict)
                        else None
                    ),
                    "capability_key": str(policy["capability_key"]),
                    "capability_domains": list(policy["domains"]),
                    "capability_needs": list(policy["needs"]),
                    "target_path": str(policy["target_path"]),
                    "evidence": evidence,
                }
            )
        status_rank = {"measured_below_reference": 0, "unmeasured": 1, "at_or_above_reference": 2}
        gaps.sort(
            key=lambda gap: (
                status_rank.get(str(gap["status"]), 9),
                -(float(gap["shortfall"]) * max(1, int(gap["weight"]))),
                str(gap["benchmark_id"]),
            )
        )
        return gaps

    @staticmethod
    def _task_gap(task) -> dict[str, Any]:
        payload = dict(getattr(task, "payload", {}) or {})
        direct = payload.get("benchmark_gap")
        if isinstance(direct, dict):
            return dict(direct)
        discovery = payload.get("discovery")
        if isinstance(discovery, dict):
            finding = discovery.get("finding")
            if isinstance(finding, dict) and isinstance(finding.get("benchmark_gap"), dict):
                return dict(finding["benchmark_gap"])
        return {}

    def quarantine_analysis(self) -> dict[str, Any]:
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        quarantined = self.queue.list(state="quarantined", limit=5000)
        for task in quarantined:
            history = list(task.failure_history)
            latest = history[-1] if history else {}
            classification = str(latest.get("classification") or "unknown")
            error = _safe_error(latest.get("error") or task.last_error or "unspecified failure")
            signature = _normalized_failure(error) or "unspecified failure"
            key = (classification, signature)
            row = groups.setdefault(
                key,
                {
                    "classification": classification,
                    "signature": signature,
                    "count": 0,
                    "example_error": error,
                    "task_ids": [],
                    "benchmark_ids": [],
                    "capability_keys": [],
                    "issue_keys": [],
                },
            )
            row["count"] += 1
            row["task_ids"].append(task.task_id)
            gap = self._task_gap(task)
            benchmark_id = str(gap.get("benchmark_id") or task.payload.get("benchmark_id") or "").strip()
            capability_key = str(task.payload.get("capability_key") or gap.get("capability_key") or "").strip()
            issue_key = str(task.payload.get("issue_key") or "").strip()
            if benchmark_id and benchmark_id not in row["benchmark_ids"]:
                row["benchmark_ids"].append(benchmark_id)
            if capability_key and capability_key not in row["capability_keys"]:
                row["capability_keys"].append(capability_key)
            if issue_key and issue_key not in row["issue_keys"]:
                row["issue_keys"].append(issue_key)

        patterns = sorted(groups.values(), key=lambda row: (-int(row["count"]), row["classification"], row["signature"]))
        directives: list[str] = []
        for pattern in patterns:
            if int(pattern["count"]) < 2:
                continue
            directive = (
                f"Repeated failure {pattern['classification']} x{pattern['count']}: do not repeat the same implementation approach. "
                f"Use new repository evidence, a different algorithm/target/provider where justified, and explicitly address: {pattern['example_error']}"
            )
            directives.append(directive[:700])
            if len(directives) >= 4:
                break
        return {
            "quarantined_tasks": len(quarantined),
            "patterns": patterns[:20],
            "strategy_directives": directives,
        }

    def _growth_tasks(self, benchmark_id: str) -> list[Any]:
        rows = []
        for task in self.queue.list(limit=5000):
            if task.payload.get("task_type") != "capability_growth":
                continue
            gap = self._task_gap(task)
            if str(gap.get("benchmark_id") or "") == benchmark_id:
                rows.append(task)
        rows.sort(key=lambda task: (int(task.payload.get("capability_generation") or 0), task.created_at))
        return rows

    def _impact_tasks(self, growth_task_id: str) -> list[Any]:
        rows = [
            task
            for task in self.queue.list(limit=5000)
            if task.payload.get("task_type") == "frontier_benchmark_measurement"
            and str(task.payload.get("impact_of_task_id") or "") == growth_task_id
        ]
        rows.sort(key=lambda task: task.created_at)
        return rows

    def impact_assessments(self, gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current = {gap["benchmark_id"]: gap for gap in gaps}
        assessments: list[dict[str, Any]] = []
        for task in self.queue.list(state="complete", limit=5000):
            if task.payload.get("task_type") != "capability_growth":
                continue
            gap = self._task_gap(task)
            benchmark_id = str(gap.get("benchmark_id") or "")
            if not benchmark_id:
                continue
            baseline = task.payload.get("baseline_score")
            try:
                baseline_score = float(baseline) if baseline is not None else None
            except (TypeError, ValueError):
                baseline_score = None
            latest = current.get(benchmark_id, {})
            current_score = latest.get("actual_score")
            measured_at = _parse_time(latest.get("measured_at"))
            promoted_at = _parse_time(task.updated_at)
            post_promotion = bool(measured_at and promoted_at and measured_at > promoted_at)
            impact_tasks = self._impact_tasks(task.task_id)
            if not post_promotion:
                status = "awaiting_post_promotion_measurement"
                delta = None
            elif baseline_score is None:
                status = "post_promotion_measurement_recorded"
                delta = None
            else:
                delta = round(float(current_score) - baseline_score, 6)
                if delta > 0:
                    status = "improved"
                elif delta < 0:
                    status = "regressed"
                else:
                    status = "no_measured_gain"
            assessments.append(
                {
                    "growth_task_id": task.task_id,
                    "benchmark_id": benchmark_id,
                    "capability_key": task.payload.get("capability_key"),
                    "capability_generation": task.payload.get("capability_generation"),
                    "baseline_score": baseline_score,
                    "current_score": current_score,
                    "delta": delta,
                    "status": status,
                    "post_promotion_measured_at": latest.get("measured_at") if post_promotion else None,
                    "measurement_task_ids": [row.task_id for row in impact_tasks],
                }
            )
        assessments.sort(key=lambda row: (str(row["benchmark_id"]), int(row.get("capability_generation") or 0)))
        return assessments

    def _ensure_impact_measurement(self, gap_by_id: dict[str, dict[str, Any]]) -> list[str]:
        created: list[str] = []
        for task in self.queue.list(state="complete", limit=5000):
            if task.payload.get("task_type") != "capability_growth":
                continue
            gap = self._task_gap(task)
            benchmark_id = str(gap.get("benchmark_id") or "")
            if not benchmark_id or self._impact_tasks(task.task_id):
                continue
            benchmark = gap_by_id.get(benchmark_id, gap)
            objective = (
                f"Re-measure Genesis on {benchmark_id} after promoted capability-growth task {task.task_id}. "
                "Use a comparable reproducible benchmark and validated provenance. Record only real measured output; "
                "never estimate, infer, or self-award improvement from the code change itself."
            )
            child, was_created = self.queue.create_unique(
                f"capability-impact:{task.task_id}:{benchmark_id}",
                objective,
                module_id="genesis.evaluation",
                priority=96,
                payload={
                    "task_type": "frontier_benchmark_measurement",
                    "benchmark": {
                        "benchmark_id": benchmark_id,
                        "family": benchmark.get("family"),
                        "reference_score": benchmark.get("reference_score"),
                        "unit": benchmark.get("unit"),
                        "weight": benchmark.get("weight"),
                    },
                    "impact_of_task_id": task.task_id,
                    "baseline_score": task.payload.get("baseline_score"),
                    "requires_provenance": True,
                    "requires_independent_validation": True,
                    "score_fabrication_forbidden": True,
                },
                max_attempts=3,
            )
            if was_created:
                created.append(child.task_id)
                self._event("impact_measurement_queued", task_id=child.task_id, growth_task_id=task.task_id, benchmark_id=benchmark_id)
        return created

    def _latest_impact(self, benchmark_id: str, assessments: list[dict[str, Any]]) -> dict[str, Any] | None:
        matches = [row for row in assessments if row.get("benchmark_id") == benchmark_id]
        if not matches:
            return None
        return max(matches, key=lambda row: int(row.get("capability_generation") or 0))

    def _growth_readiness(
        self,
        gap: dict[str, Any],
        assessments: list[dict[str, Any]],
    ) -> tuple[bool, str, int]:
        tasks = self._growth_tasks(str(gap["benchmark_id"]))
        if not tasks:
            return True, "first_measured_growth_generation", 1
        latest = tasks[-1]
        generation = int(latest.payload.get("capability_generation") or len(tasks) or 1)
        if latest.state not in TERMINAL_GROWTH_STATES:
            return False, f"growth_task_{latest.state}", generation
        if latest.state in {"quarantined", "cancelled"}:
            return True, f"previous_growth_{latest.state}", generation + 1
        impact = self._latest_impact(str(gap["benchmark_id"]), assessments)
        if impact is None or impact.get("growth_task_id") != latest.task_id:
            return False, "awaiting_impact_assessment", generation
        if impact.get("status") == "awaiting_post_promotion_measurement":
            return False, "awaiting_post_promotion_measurement", generation
        if gap.get("status") != "measured_below_reference":
            return False, "benchmark_gap_closed", generation
        return True, f"impact_{impact.get('status')}", generation + 1

    @staticmethod
    def _target_evidence(path: Path) -> str:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            value = line.strip()
            if len(value) >= 20 and not value.startswith(("import ", "from ", "#")):
                return value[:1000]
        return text[:1000].strip()

    def _ensure_growth_task(
        self,
        focus: dict[str, Any],
        quarantine: dict[str, Any],
        assessments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if focus.get("status") != "measured_below_reference":
            return {"status": "measurement_required", "benchmark_id": focus.get("benchmark_id")}

        ready, reason, generation = self._growth_readiness(focus, assessments)
        if not ready:
            return {"status": "deferred", "reason": reason, "benchmark_id": focus.get("benchmark_id")}

        # A validated benchmark deficit is durable priority-95 work. Do not let an
        # unrelated lower-priority pipeline record prevent a new growth generation
        # from being registered after the previous generation was quarantined or
        # cancelled. The shared scheduler/review gates still serialize execution and
        # preserve review/validation priority; this only removes the creation-time
        # starvation point.
        concurrent_pipeline_task_ids = [record.task_id for record in self.pipeline.list_active()[:20]]

        target = self.root / str(focus["target_path"])
        if not target.is_file():
            return {"status": "blocked", "reason": "capability_target_missing", "target_path": str(focus["target_path"])}
        target_evidence = self._target_evidence(target)
        if not target_evidence:
            return {"status": "blocked", "reason": "capability_target_has_no_grounding_evidence", "target_path": str(focus["target_path"])}

        relevant_directives = []
        for directive in quarantine.get("strategy_directives", []):
            if directive not in relevant_directives:
                relevant_directives.append(directive)
            if len(relevant_directives) >= 3:
                break
        strategy = " ".join(relevant_directives)
        needs = "; ".join(str(value) for value in focus.get("capability_needs", []))
        objective = (
            f"Improve the measured Genesis capability gap for benchmark {focus['benchmark_id']} ({focus['family']}). "
            f"Validated baseline is {focus['actual_score']}/{focus['reference_score']} {focus['unit']}. "
            f"Capability needs: {needs}. Target exactly {focus['target_path']}. "
            "Make one bounded evidence-driven capability improvement; do not optimize the scorer or hard-code benchmark answers. "
            "Success is not the code change itself: after independent validation and promotion, the same comparable benchmark must be re-run and show real measured improvement. "
            "Preserve tests, Security, governance, provenance, protected-file, signing, and owner boundaries."
        )
        if strategy:
            objective += " FAILURE_STRATEGY: " + strategy

        benchmark_gap = dict(focus)
        benchmark_gap["growth_generation"] = generation
        finding = {
            "decision": "upgrade",
            "kind": "existing_upgrade",
            "target_path": str(focus["target_path"]),
            "summary": (
                f"Add or strengthen {focus['capability_key']} capability to improve validated {focus['benchmark_id']} performance."
            ),
            "acceptance": (
                "Candidate passes repository tests and all review/validation gates; after promotion a comparable independently validated benchmark re-measurement is queued. "
                "The capability is considered effective only if that measured score improves over the stored baseline."
            ),
            "learning_evidence": str(focus["evidence"]),
            "target_evidence": target_evidence,
            "confidence_normalized": 1.0,
            "grounded": True,
            "new_capability": False,
            "capability_key": str(focus["capability_key"]),
            "capability_domains": list(focus.get("capability_domains", [])),
            "lesson": f"Improve {focus['family']} capability based on a validated benchmark deficit.",
            "lesson_evidence": str(focus["evidence"]),
            "lesson_topics": list(focus.get("capability_needs", [])),
            "benchmark_gap": benchmark_gap,
            "strategy_directives": relevant_directives,
        }
        context_paths = [str(focus["target_path"])]
        test_candidate = self.root / "tests" / f"test_{Path(str(focus['target_path'])).stem}.py"
        if test_candidate.is_file():
            context_paths.append(test_candidate.relative_to(self.root).as_posix())

        task, created = self.queue.create_unique(
            f"capability-growth:{focus['benchmark_id']}:generation:{generation}",
            objective,
            module_id="genesis.coding",
            priority=95,
            payload={
                "source": "genesis.evolution_learning",
                "task_type": "capability_growth",
                "target_path": str(focus["target_path"]),
                "context_paths": context_paths,
                "capability_key": str(focus["capability_key"]),
                "capability_generation": generation,
                "benchmark_gap": benchmark_gap,
                "baseline_score": focus.get("actual_score"),
                "baseline_measured_at": focus.get("measured_at"),
                "discovery": {"finding": finding},
                "score_fabrication_forbidden": True,
                "requires_independent_validation": True,
            },
            max_attempts=4,
        )
        discovery = {
            "status": "capability_growth_enqueued" if created else "capability_growth_already_known",
            "source": "genesis.evolution_learning",
            "task_id": task.task_id,
            "target": str(focus["target_path"]),
            "benchmark_gap": benchmark_gap,
            "capability_key": str(focus["capability_key"]),
            "capability_generation": generation,
            "finding": finding,
        }
        self.pipeline.register_discovery(task.task_id, str(focus["target_path"]), discovery)
        if created:
            self._event(
                "capability_growth_queued",
                task_id=task.task_id,
                benchmark_id=focus["benchmark_id"],
                capability_key=focus["capability_key"],
                generation=generation,
                baseline_score=focus.get("actual_score"),
                concurrent_pipeline_task_ids=concurrent_pipeline_task_ids,
            )
        return {
            "status": "created" if created else "existing",
            "task_id": task.task_id,
            "benchmark_id": focus["benchmark_id"],
            "capability_key": focus["capability_key"],
            "capability_generation": generation,
            "readiness_reason": reason,
            "concurrent_pipeline_task_ids": concurrent_pipeline_task_ids,
        }

    def _event(self, event: str, **details: object) -> None:
        row = {"at": utc_now(), "event": event, **details}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def run_once(self) -> dict[str, Any]:
        from .competitive_benchmarks import CompetitiveBenchmarkPlanner

        benchmark_plan = CompetitiveBenchmarkPlanner(self.root).ensure_tasks()
        gaps = self.benchmark_gaps()
        actionable = [gap for gap in gaps if gap["status"] != "at_or_above_reference"]
        focus = actionable[0] if actionable else None
        quarantine = self.quarantine_analysis()
        gap_by_id = {str(gap["benchmark_id"]): gap for gap in gaps}
        impact_tasks_created = self._ensure_impact_measurement(gap_by_id)
        assessments = self.impact_assessments(gaps)
        if focus is None:
            growth_work = {"status": "no_capability_gap"}
        else:
            growth_work = self._ensure_growth_task(focus, quarantine, assessments)

        payload = {
            "created_at": utc_now(),
            "version": ROUTING_VERSION,
            "focus": focus,
            "gaps": gaps,
            "benchmark_plan": benchmark_plan,
            "quarantine_analysis": quarantine,
            "impact_measurement_tasks_created": impact_tasks_created,
            "impact_assessments": assessments,
            "growth_work": growth_work,
            "policy": {
                "unmeasured_is_evidence_gap_not_capability_failure": True,
                "capability_growth_requires_validated_below_reference_measurement": True,
                "promotion_does_not_equal_improvement": True,
                "improvement_requires_post_promotion_validated_remeasurement": True,
                "score_fabrication_forbidden": True,
            },
        }
        self.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload


def install_capability_evolution_controller() -> None:
    """Run capability-gap control before every evolution-learning cycle.

    The wrapper is deliberately installed after new-capability routing. It does not
    create a second promotion path; it can only register work in the same shared
    queue and PipelineStore already used by Genesis development/review/validation.
    """
    from .evolution_learning import GenesisEvolutionLearningEngine

    if getattr(GenesisEvolutionLearningEngine, "_genesis_capability_evolution", None) == ROUTING_VERSION:
        return

    original_run_once = GenesisEvolutionLearningEngine.run_once

    def run_once(self):
        control = CapabilityEvolutionController(
            self.root,
            queue=self.queue,
            pipeline=self.pipeline,
        ).run_once()
        self.capability_evolution_focus = control.get("focus")
        self.capability_strategy_directives = list(
            (control.get("quarantine_analysis") or {}).get("strategy_directives") or []
        )

        growth = dict(control.get("growth_work") or {})
        if growth.get("status") in {"created", "existing"} and growth.get("task_id"):
            return {
                "status": "capability_gap_work_ready",
                "capability_evolution": control,
                "active_task_ids": [growth["task_id"]],
                "learning_queue": self.store.research_queue_summary(),
            }

        result = original_run_once(self)
        if isinstance(result, dict):
            result = dict(result)
            result["capability_evolution"] = control
        return result

    GenesisEvolutionLearningEngine.run_once = run_once
    GenesisEvolutionLearningEngine._genesis_capability_evolution = ROUTING_VERSION

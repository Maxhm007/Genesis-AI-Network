from __future__ import annotations

from dataclasses import replace
from typing import Any


IMPROVEMENT_MODULE_ID = "genesis.improvement"
LEARNED_CAPABILITY_TARGET = "genesis/learned_capabilities.py"


class ImprovementModule:
    """Own bounded improvements to existing Genesis capabilities.

    New capability creation remains with the Self Development/Development path.
    This module only improves an existing implementation in response to measured
    evidence and never receives merge/promotion authority.
    """

    @staticmethod
    def _payload(task: Any) -> dict:
        payload = getattr(task, "payload", {}) or {}
        return dict(payload) if isinstance(payload, dict) else {}

    @classmethod
    def is_improvement_task(cls, task: Any, record: Any | None = None) -> bool:
        if task is None:
            return False
        payload = cls._payload(task)
        task_type = str(payload.get("task_type") or "").strip().lower()
        source = str(payload.get("source") or "").strip()
        target = str(getattr(record, "target_path", "") or payload.get("target_path") or "")
        target = target.replace("\\", "/").lstrip("./")

        discovery = payload.get("discovery")
        finding = discovery.get("finding") if isinstance(discovery, dict) else None
        direct_finding = payload.get("finding")
        if not isinstance(finding, dict):
            finding = direct_finding if isinstance(direct_finding, dict) else {}

        if task_type == "new_capability" or bool(finding.get("new_capability")):
            return False
        if target == LEARNED_CAPABILITY_TARGET:
            return False
        if task_type == "capability_growth":
            return True
        return source == "genesis.evolution_learning" and bool(target)

    @classmethod
    def prepare_task(cls, task: Any, record: Any | None = None):
        """Return a task view with an improvement-only objective and provenance.

        The persistent task itself is not rewritten; the bounded worker receives a
        stricter objective for this attempt while the original queue evidence stays
        immutable.
        """
        payload = cls._payload(task)
        gap = payload.get("benchmark_gap") if isinstance(payload.get("benchmark_gap"), dict) else {}
        if not gap:
            discovery = payload.get("discovery")
            if isinstance(discovery, dict):
                finding = discovery.get("finding")
                if isinstance(finding, dict) and isinstance(finding.get("benchmark_gap"), dict):
                    gap = dict(finding["benchmark_gap"])

        capability_key = str(payload.get("capability_key") or gap.get("capability_key") or "existing_capability")
        benchmark_id = str(gap.get("benchmark_id") or payload.get("benchmark_id") or "unmeasured")
        baseline = payload.get("baseline_score")
        reference = gap.get("reference_score")
        strategy = payload.get("strategy_change_directive") or payload.get("strategy_directive") or ""
        if not strategy and isinstance(payload.get("strategy_directives"), list):
            strategy = " | ".join(str(item) for item in payload["strategy_directives"][:3])

        objective = (
            "ROLE: genesis_improvement_submodule\n"
            "Improve an EXISTING Genesis capability only. Do not invent an unrelated capability, "
            "do not expand scope beyond the approved target, and do not merge or promote your own candidate.\n"
            f"CAPABILITY_KEY: {capability_key}\n"
            f"BENCHMARK_ID: {benchmark_id}\n"
            f"BASELINE_SCORE: {baseline if baseline is not None else 'unknown'}\n"
            f"REFERENCE_SCORE: {reference if reference is not None else 'unknown'}\n"
            "SUCCESS_RULE: produce the smallest test-grounded candidate that addresses the measured deficit; "
            "preserve Security, review, independent validation, provenance, protected files, and rollback boundaries. "
            "A code change is not capability improvement until the benchmark is remeasured after promotion.\n"
        )
        if strategy:
            objective += (
                "STRATEGY_CHANGE: Previous evidence requires a meaningfully different approach; explicitly address: "
                + str(strategy)[:1600]
                + "\n"
            )
        objective += "\nORIGINAL_OBJECTIVE:\n" + str(getattr(task, "objective", ""))

        enriched_payload = dict(payload)
        enriched_payload["active_submodule"] = IMPROVEMENT_MODULE_ID
        enriched_payload["improvement_capability_key"] = capability_key
        enriched_payload["improvement_benchmark_id"] = benchmark_id
        return replace(task, objective=objective, module_id=IMPROVEMENT_MODULE_ID, payload=enriched_payload)

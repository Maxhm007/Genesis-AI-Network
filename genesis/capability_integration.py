from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .evaluation import EvaluationModule
from .evidence import EvidenceModule
from .experiment import ExperimentModule
from .model_scout import ModelScoutModule
from .resource import ResourceModule, ResourceSnapshot


@dataclass(frozen=True)
class MeasuredProviderProfile:
    name: str
    samples: int
    reliability: float
    resource_cost: float
    capabilities: tuple[str, ...]


class ProviderTelemetryStore:
    """Persist observed provider outcomes for evidence-backed routing.

    Routing profiles are exposed only after MIN_ROUTING_SAMPLES so one isolated
    success or failure cannot immediately steer Genesis toward or away from a
    provider.
    """

    MIN_ROUTING_SAMPLES = 3

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "providers": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload.get("providers"), dict):
                raise ValueError
            return payload
        except Exception:
            return {"version": 1, "providers": {}}

    def record(self, *, provider: str, capability: str, quality: float, success: bool,
               resource_cost: float, evidence_count: int) -> dict:
        if not provider.strip() or not capability.strip():
            raise ValueError("provider and capability are required")
        if evidence_count <= 0:
            raise ValueError("measured provider telemetry requires evidence")
        quality = max(0.0, min(1.0, float(quality)))
        resource_cost = max(0.01, float(resource_cost))
        payload = self._load()
        rows = payload["providers"]
        row = dict(rows.get(provider, {}))
        samples = int(row.get("samples", 0)) + 1
        successes = int(row.get("successes", 0)) + (1 if success else 0)
        quality_total = float(row.get("quality_total", 0.0)) + quality
        resource_total = float(row.get("resource_total", 0.0)) + resource_cost
        capabilities = sorted(set(row.get("capabilities", [])) | {capability.strip().lower()})
        rows[provider] = {
            "samples": samples,
            "successes": successes,
            "quality_total": quality_total,
            "resource_total": resource_total,
            "capabilities": capabilities,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self.summary(provider)

    def summary(self, provider: str) -> dict:
        row = self._load().get("providers", {}).get(provider)
        if not row:
            return {"provider": provider, "samples": 0, "routing_ready": False}
        samples = max(1, int(row["samples"]))
        success_rate = int(row["successes"]) / samples
        average_quality = float(row["quality_total"]) / samples
        reliability = max(0.0, min(1.0, (0.6 * success_rate) + (0.4 * average_quality)))
        resource_cost = max(0.01, float(row["resource_total"]) / samples)
        return {
            "provider": provider,
            "samples": samples,
            "success_rate": round(success_rate, 4),
            "average_quality": round(average_quality, 4),
            "reliability": round(reliability, 4),
            "resource_cost": round(resource_cost, 6),
            "capabilities": tuple(row.get("capabilities", [])),
            "routing_ready": samples >= self.MIN_ROUTING_SAMPLES,
        }

    def measured_profile(self, provider: str) -> MeasuredProviderProfile | None:
        summary = self.summary(provider)
        if not summary.get("routing_ready"):
            return None
        return MeasuredProviderProfile(
            name=provider,
            samples=int(summary["samples"]),
            reliability=float(summary["reliability"]),
            resource_cost=float(summary["resource_cost"]),
            capabilities=tuple(summary["capabilities"]),
        )


class CapabilityGrowthCoordinator:
    """Connect Evaluation → Experiment → Model Scout → routing telemetry.

    This coordinator measures and recommends. It does not activate models,
    validate its own evidence, promote code, or lease remote work automatically.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.evaluation = EvaluationModule()
        self.experiment = ExperimentModule()
        self.models = ModelScoutModule()
        self.evidence = EvidenceModule()
        self.resources = ResourceModule()
        self.telemetry = ProviderTelemetryStore(self.root / "runtime" / "provider_telemetry.json")

    def observe_provider(self, *, provider: str, capability: str, score: float,
                         max_score: float, baseline_score: float, resource_cost: float,
                         success: bool, evidence_count: int, source: str, provenance: str,
                         snapshot: ResourceSnapshot | None = None) -> dict:
        evaluation = self.evaluation.evaluate(capability, score, max_score, evidence_count)
        baseline_normalized = max(0.0, min(1.0, baseline_score / max_score))
        experiment = self.experiment.compare(
            f"{provider} improves {capability}",
            baseline_normalized,
            evaluation.normalized,
            minimum_gain=0.01,
        )

        record = self.evidence.record(
            claim=f"{provider} measured {evaluation.score}/{evaluation.max_score} on {capability}",
            source=source,
            provenance=provenance,
            confidence=evaluation.normalized,
        )
        if evidence_count > 0:
            record = self.evidence.transition(record, "reviewed")

        candidate = self.models.candidate(provider, source, "provider-declared; verify license independently")
        candidate = self.models.transition(candidate, "quarantined")
        candidate = self.models.transition(
            candidate,
            "tested",
            benchmark_score=evaluation.normalized,
            resource_cost=resource_cost,
        )
        next_model_state = "validated" if experiment.decision == "keep" and success and evidence_count > 0 else None

        telemetry = self.telemetry.record(
            provider=provider,
            capability=capability,
            quality=evaluation.normalized,
            success=success,
            resource_cost=resource_cost,
            evidence_count=evidence_count,
        )

        capacity = None
        execution_scope = "local"
        if snapshot is not None:
            capacity = self.resources.capacity_score(snapshot)
            if snapshot.network_available and capacity < 25:
                execution_scope = "peer_candidate"

        return {
            "evaluation": evaluation.as_dict(),
            "experiment": experiment.as_dict(),
            "evidence": record.as_dict(),
            "model_candidate": candidate.as_dict(),
            "recommended_model_transition": next_model_state,
            "telemetry": telemetry,
            "resource_capacity": capacity,
            "recommended_execution_scope": execution_scope,
            "automatic_activation": False,
            "automatic_peer_lease": False,
        }

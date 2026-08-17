from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json


TRUST_STATES = ("discovered", "quarantined", "tested", "validated", "trusted", "active")


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    source: str
    license: str
    state: str = "discovered"
    benchmark_score: float | None = None
    resource_cost: float | None = None
    capabilities: tuple[str, ...] = ()
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ModelRecommendation:
    name: str
    state: str
    recommendation: str
    score: float
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class ModelScoutModule:
    """Discover, rank and qualify replaceable intelligence providers.

    Discovery or recommendation never activates a model. Activation still
    requires the full trust lifecycle and benchmark evidence.
    """

    def candidate(
        self,
        name: str,
        source: str,
        license: str,
        *,
        capabilities: tuple[str, ...] | list[str] = (),
        notes: str = "",
    ) -> ModelCandidate:
        if not name.strip() or not source.strip() or not license.strip():
            raise ValueError("name, source and license are required")
        return ModelCandidate(
            name.strip(),
            source.strip(),
            license.strip(),
            capabilities=tuple(str(item).strip() for item in capabilities if str(item).strip()),
            notes=notes.strip(),
        )

    def transition(
        self,
        candidate: ModelCandidate,
        new_state: str,
        *,
        benchmark_score: float | None = None,
        resource_cost: float | None = None,
    ) -> ModelCandidate:
        if new_state not in TRUST_STATES:
            raise ValueError("unknown trust state")
        current = TRUST_STATES.index(candidate.state)
        target = TRUST_STATES.index(new_state)
        if target != current + 1:
            raise ValueError("model trust lifecycle must advance one state at a time")
        if new_state in {"validated", "trusted", "active"} and benchmark_score is None and candidate.benchmark_score is None:
            raise ValueError("validated-or-higher model requires benchmark evidence")
        return ModelCandidate(
            candidate.name,
            candidate.source,
            candidate.license,
            new_state,
            candidate.benchmark_score if benchmark_score is None else float(benchmark_score),
            candidate.resource_cost if resource_cost is None else float(resource_cost),
            candidate.capabilities,
            candidate.notes,
        )

    @staticmethod
    def _ranking_score(candidate: ModelCandidate) -> float:
        benchmark = max(0.0, float(candidate.benchmark_score or 0.0))
        cost = max(0.05, float(candidate.resource_cost or 1.0))
        state_bonus = TRUST_STATES.index(candidate.state) * 5.0
        evidence_bonus = 5.0 if candidate.benchmark_score is not None else 0.0
        capability_bonus = min(len(candidate.capabilities), 6) * 0.5
        return (benchmark / cost) + state_bonus + evidence_bonus + capability_bonus

    def recommend(
        self,
        candidates: list[ModelCandidate] | tuple[ModelCandidate, ...],
        *,
        max_resource_cost: float | None = None,
        capability: str | None = None,
        limit: int = 5,
    ) -> list[ModelRecommendation]:
        """Recommend what Genesis should evaluate or activate next.

        Discovered/quarantined/tested models may be recommended for evaluation,
        never for activation. Only validated/trusted models may be recommended
        for activation, and active models are reported as already active.
        """
        wanted = (capability or "").strip().lower()
        ranked: list[tuple[float, ModelCandidate]] = []
        for candidate in candidates:
            if max_resource_cost is not None and candidate.resource_cost is not None and candidate.resource_cost > max_resource_cost:
                continue
            if wanted and wanted not in {item.lower() for item in candidate.capabilities}:
                continue
            ranked.append((self._ranking_score(candidate), candidate))
        ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))

        output: list[ModelRecommendation] = []
        for score, candidate in ranked[: max(1, min(limit, 20))]:
            if candidate.state == "active":
                recommendation = "keep_active_and_monitor"
                reason = "model is already active; continue telemetry and regression monitoring"
            elif candidate.state in {"validated", "trusted"}:
                recommendation = "candidate_for_activation"
                reason = "benchmark evidence exists; compare against the current active provider before activation"
            else:
                recommendation = "evaluate_next"
                reason = "model is not trusted enough for activation; advance only through quarantine, testing and validation"
            output.append(ModelRecommendation(candidate.name, candidate.state, recommendation, round(score, 4), reason))
        return output

    def load_seed_candidates(self, path: Path) -> list[ModelCandidate]:
        if not Path(path).is_file():
            return []
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.get("candidates", []) if isinstance(payload, dict) else []
        candidates: list[ModelCandidate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidates.append(
                ModelCandidate(
                    name=str(row.get("name", "")).strip(),
                    source=str(row.get("source", "")).strip(),
                    license=str(row.get("license", "")).strip(),
                    state=str(row.get("state", "discovered")).strip(),
                    benchmark_score=(None if row.get("benchmark_score") is None else float(row["benchmark_score"])),
                    resource_cost=(None if row.get("resource_cost") is None else float(row["resource_cost"])),
                    capabilities=tuple(str(item) for item in row.get("capabilities", []) if str(item).strip()),
                    notes=str(row.get("notes", "")).strip(),
                )
            )
        return [candidate for candidate in candidates if candidate.name and candidate.source and candidate.license and candidate.state in TRUST_STATES]

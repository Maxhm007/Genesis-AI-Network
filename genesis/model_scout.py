from __future__ import annotations

from dataclasses import dataclass, asdict


TRUST_STATES = ("discovered", "quarantined", "tested", "validated", "trusted", "active")


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    source: str
    license: str
    state: str = "discovered"
    benchmark_score: float | None = None
    resource_cost: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class ModelScoutModule:
    """Provider/model candidate lifecycle without automatic activation."""

    def candidate(self, name: str, source: str, license: str) -> ModelCandidate:
        if not name.strip() or not source.strip() or not license.strip():
            raise ValueError("name, source and license are required")
        return ModelCandidate(name.strip(), source.strip(), license.strip())

    def transition(self, candidate: ModelCandidate, new_state: str, *, benchmark_score: float | None = None,
                   resource_cost: float | None = None) -> ModelCandidate:
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
        )

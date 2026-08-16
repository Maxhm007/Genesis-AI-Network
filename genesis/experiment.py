from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ExperimentDecision:
    hypothesis: str
    baseline: float
    candidate: float
    delta: float
    decision: str

    def as_dict(self) -> dict:
        return asdict(self)


class ExperimentModule:
    """Compare bounded candidates against a measured baseline."""

    def compare(self, hypothesis: str, baseline: float, candidate: float, minimum_gain: float = 0.0) -> ExperimentDecision:
        hypothesis = hypothesis.strip()
        if not hypothesis:
            raise ValueError("hypothesis is required")
        delta = float(candidate) - float(baseline)
        decision = "keep" if delta > float(minimum_gain) else "reject"
        return ExperimentDecision(hypothesis, float(baseline), float(candidate), delta, decision)

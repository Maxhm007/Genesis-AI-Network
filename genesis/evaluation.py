from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    score: float
    max_score: float
    evidence_count: int

    @property
    def normalized(self) -> float:
        return 0.0 if self.max_score <= 0 else max(0.0, min(1.0, self.score / self.max_score))

    def as_dict(self) -> dict:
        data = asdict(self)
        data["normalized"] = self.normalized
        return data


class EvaluationModule:
    """Evidence-first capability evaluation.

    Unmeasured capability receives zero credit. Architectural presence alone is
    not benchmark evidence.
    """

    def evaluate(self, name: str, score: float | None, max_score: float, evidence_count: int = 0) -> EvaluationResult:
        if max_score <= 0:
            raise ValueError("max_score must be positive")
        measured = float(score) if score is not None and evidence_count > 0 else 0.0
        return EvaluationResult(name, max(0.0, min(float(max_score), measured)), float(max_score), max(0, int(evidence_count)))

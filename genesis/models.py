from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelAssessment:
    model_id: str
    status: str
    score: int
    reasons: list[str]
    license: str | None
    downloads: int | None
    likes: int | None


class ModelEvaluator:
    """Conservative metadata-only model assessment.

    V0.1 never downloads or executes discovered model code. A model can only
    become `review_candidate`; actual trust requires later sandbox benchmarks,
    security tests, license checks and independent validation.
    """

    ACCEPTABLE_LICENSE_HINTS = {
        "apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "cc-by-4.0"
    }

    def assess(self, item: dict[str, Any]) -> ModelAssessment:
        model_id = str(item.get("id") or item.get("modelId") or item.get("name") or "unknown")
        license_value = item.get("license") or item.get("license", "unknown")
        if not license_value:
            card = item.get("cardData") or {}
            license_value = card.get("license") if isinstance(card, dict) else None
        license_text = str(license_value).lower() if license_value else None
        downloads = self._int_or_none(item.get("downloads"))
        likes = self._int_or_none(item.get("likes"))

        score = 0
        reasons: list[str] = []
        if license_text in self.ACCEPTABLE_LICENSE_HINTS:
            score += 3
            reasons.append("recognized permissive/open license metadata")
        elif license_text:
            reasons.append("license requires manual policy review")
        else:
            reasons.append("license metadata missing")

        if downloads is not None and downloads >= 1000:
            score += 1
            reasons.append("has meaningful public usage signal")
        if likes is not None and likes >= 10:
            score += 1
            reasons.append("has public interest signal")

        pipeline_tag = item.get("pipeline_tag") or item.get("pipelineTag")
        if pipeline_tag:
            score += 1
            reasons.append(f"declares capability: {pipeline_tag}")

        status = "review_candidate" if score >= 3 and license_text else "quarantined_metadata"
        return ModelAssessment(model_id, status, score, reasons, license_text, downloads, likes)

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

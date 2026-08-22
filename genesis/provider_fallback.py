from __future__ import annotations

from .autonomous_engineering import AutonomousEngineeringLoop
from .intelligence_router import IntelligenceRouter


INSTALL_MARKER = "_genesis_provider_fallback_installed"


def _is_qwen(provider) -> bool:
    return "qwen" in str(getattr(provider, "name", "")).strip().lower()


def _select_eligible_coding_provider(self: AutonomousEngineeringLoop):
    """Choose the best available bounded coding provider, with Qwen as fallback.

    Genesis previously excluded Qwen from code generation even though Gene Pulse
    provisioned Qwen as its only model runtime. That policy could park otherwise
    executable self-development tasks forever. Selection is now capability- and
    evidence-driven: bootstrap is still excluded from coding, measured reliability
    wins first, a non-Qwen provider wins an exact reliability tie, then lower
    resource cost/name break remaining ties. If Qwen is the only eligible coding
    provider it is used and remains subject to the normal bounded edit, tests,
    Security, review, independent validation, provenance, and promotion gates.
    """
    candidates = []
    for provider in self.providers.available_providers():
        try:
            profile, _source = self.coding.router._effective_profile(provider)
        except Exception:
            profile = IntelligenceRouter.profile(provider)
        if profile.name == "genesis-bootstrap":
            continue
        if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
            continue
        candidates.append(
            (
                -float(profile.reliability),
                1 if _is_qwen(provider) else 0,
                float(profile.resource_cost),
                profile.name,
                provider,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:4])
    return candidates[0][4]


def install_provider_fallback() -> None:
    """Install the provider-selection repair once for every Genesis entrypoint."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._coding_provider = _select_eligible_coding_provider
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

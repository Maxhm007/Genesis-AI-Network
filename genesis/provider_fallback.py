from __future__ import annotations

from types import MethodType

from .autonomous_engineering import AutonomousEngineeringLoop
from .intelligence_router import IntelligenceRouter


INSTALL_MARKER = "_genesis_provider_fallback_installed"
LEARNED_CAPABILITY_TARGET = "genesis/learned_capabilities.py"
_ORIGINAL_CODING_PROVIDER = AutonomousEngineeringLoop._coding_provider
_ORIGINAL_ATTEMPT_TASK = AutonomousEngineeringLoop._attempt_task


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


def _requires_grounded_capability_builder(task) -> bool:
    """Keep open-ended learned capability creation on its deterministic builder."""
    payload = getattr(task, "payload", {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    target = str(payload.get("target_path") or "").replace("\\", "/").lstrip("./")
    task_type = str(payload.get("task_type") or "").strip().lower()
    finding = payload.get("finding")
    discovery = payload.get("discovery")
    if not isinstance(finding, dict) and isinstance(discovery, dict):
        finding = discovery.get("finding")
    new_capability = bool(finding.get("new_capability")) if isinstance(finding, dict) else False
    return target == LEARNED_CAPABILITY_TARGET or task_type == "new_capability" or new_capability


def _attempt_task_with_provider_fallback(self: AutonomousEngineeringLoop, task, runtime):
    """Use Qwen for grounded code work but not unsupported capability invention."""
    if not _requires_grounded_capability_builder(task):
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        result["provider_policy"] = "eligible_provider_with_qwen_fallback"
        if result.get("coding_strategy") == "external_non_qwen_provider":
            result["coding_strategy"] = "eligible_model_provider"
        if result.get("error") == "no_non_qwen_coding_provider_available":
            result["error"] = "no_eligible_coding_provider_available"
        return result

    # New learned capabilities remain evidence-gated: the deterministic builder
    # gets first chance inside the original attempt. If it cannot ground a safe
    # implementation, restore the previous non-Qwen selector for this one task so
    # a small local model cannot fabricate an unsupported capability.
    had_override = "_coding_provider" in self.__dict__
    previous_override = self.__dict__.get("_coding_provider")
    self._coding_provider = MethodType(_ORIGINAL_CODING_PROVIDER, self)
    try:
        return _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
    finally:
        if had_override:
            self.__dict__["_coding_provider"] = previous_override
        else:
            self.__dict__.pop("_coding_provider", None)


def install_provider_fallback() -> None:
    """Install the provider-selection repair once for every Genesis entrypoint."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._coding_provider = _select_eligible_coding_provider
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_provider_fallback
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

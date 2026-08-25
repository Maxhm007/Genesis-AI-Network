from __future__ import annotations

from .autonomous_engineering import AutonomousEngineeringLoop
from .coding import CodingModule
from .intelligence_router import IntelligenceRouter
from .providers import GenesisHTTPProvider


INSTALL_MARKER = "_genesis_coding_provider_policy_installed"
CODING_ROLE = "bounded_coding_engineer"
TRANSPORT_CODING_ROLE = "bounded_coding_engineer_full_budget"
MAX_BOUNDED_EDITS = 2
_ORIGINAL_HTTP_REASON = GenesisHTTPProvider.reason
_ORIGINAL_CODING_PROPOSE = CodingModule.propose


def _is_qwen(provider) -> bool:
    return "qwen" in str(getattr(provider, "name", "")).strip().lower()


def _select_quality_first_provider(self: AutonomousEngineeringLoop):
    """Prefer a non-Qwen eligible coder, while retaining Qwen as a live fallback.

    The previous provider hook made Qwen win purely because of its name. That is
    useful for lineage experiments, but harmful when a stronger coding provider is
    also available. This policy keeps Qwen usable when it is the only trained
    coder, while preventing it from pre-empting another eligible provider.
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
                1 if _is_qwen(provider) else 0,
                -float(profile.reliability),
                float(profile.resource_cost),
                profile.name,
                provider,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:4])
    return candidates[0][4]


def _is_coding_prompt(prompt: str) -> bool:
    return any(
        line.strip() == f"ROLE: {CODING_ROLE}"
        for line in str(prompt).splitlines()[:8]
    )


def _transport_prompt(prompt: str) -> str:
    """Use the provider's configured bounded budget for coding requests.

    Both the HTTP client and local reasoning server historically special-cased
    ``bounded_coding_engineer`` to 256 output tokens. The workflows already run
    with a bounded provider cap (768 tokens after the local server's hard cap), so
    a transport-only role alias removes the accidental 256-token choke point
    without changing any execution or promotion boundary.

    HTTP repair providers are also allowed a second tightly related compact edit
    when necessary for the same objective, such as implementation plus regression
    coverage. The ordinary CodingModule contract stays one-edit by default.
    """
    if not _is_coding_prompt(prompt):
        return prompt

    value = str(prompt).replace(
        f"ROLE: {CODING_ROLE}",
        f"ROLE: {TRANSPORT_CODING_ROLE}",
        1,
    )
    replacements = (
        ("Make exactly ONE smallest useful edit", "Make one or two smallest useful edits"),
        ("RULES: exactly one edit;", "RULES: one or two tightly related edits;"),
        ("Exactly one edit.", "One or two tightly related edits."),
        ("Return only the required one-edit JSON.", "Return only the required bounded edits JSON."),
    )
    for old, new in replacements:
        value = value.replace(old, new)

    marker = f"ROLE: {TRANSPORT_CODING_ROLE}\n"
    guidance = (
        "EDIT_BUDGET: Prefer one edit. A second edit is allowed only when it is tightly related and "
        "needed to complete the same objective, such as implementation plus regression coverage. "
        "Never broaden scope merely because a second edit is available.\n"
    )
    if marker in value and guidance not in value:
        value = value.replace(marker, marker + guidance, 1)
    return value


def _reason_with_resilient_coding_policy(self: GenesisHTTPProvider, prompt: str) -> str:
    return _ORIGINAL_HTTP_REASON(self, _transport_prompt(prompt))


def _propose_with_scoped_http_edit_budget(
    self: CodingModule,
    objective: str,
    context_paths: list[str] | None = None,
    *,
    provider=None,
):
    """Permit at most two compact edits only for the bounded HTTP repair lane."""
    selected = provider or self._provider()
    if selected is None or not isinstance(selected, GenesisHTTPProvider):
        return _ORIGINAL_CODING_PROPOSE(self, objective, context_paths, provider=selected)

    had_override = "MAX_EDITS" in self.__dict__
    previous_override = self.__dict__.get("MAX_EDITS")
    self.MAX_EDITS = MAX_BOUNDED_EDITS
    try:
        return _ORIGINAL_CODING_PROPOSE(self, objective, context_paths, provider=selected)
    finally:
        if had_override:
            self.__dict__["MAX_EDITS"] = previous_override
        else:
            self.__dict__.pop("MAX_EDITS", None)


def install_coding_provider_policy() -> None:
    """Install the bounded autonomous coding reliability policy once."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return

    AutonomousEngineeringLoop._coding_provider = _select_quality_first_provider
    GenesisHTTPProvider.reason = _reason_with_resilient_coding_policy
    CodingModule.propose = _propose_with_scoped_http_edit_budget
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

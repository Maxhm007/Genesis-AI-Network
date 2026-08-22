from __future__ import annotations

from types import MethodType

from .autonomous_engineering import AutonomousEngineeringLoop
from .intelligence_router import IntelligenceRouter


INSTALL_MARKER = "_genesis_provider_fallback_installed"
LEARNED_CAPABILITY_TARGET = "genesis/learned_capabilities.py"
LEARNED_CAPABILITY_MARKER = "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT"
_ORIGINAL_CODING_PROVIDER = AutonomousEngineeringLoop._coding_provider
_ORIGINAL_ATTEMPT_TASK = AutonomousEngineeringLoop._attempt_task


def _is_qwen(provider) -> bool:
    return "qwen" in str(getattr(provider, "name", "")).strip().lower()


def _select_eligible_coding_provider(self: AutonomousEngineeringLoop):
    """Choose the best available bounded non-Qwen coding provider.

    Selection is capability- and evidence-driven: bootstrap and Qwen providers are
    excluded, measured reliability wins first, then lower resource cost/name break
    remaining ties. This preserves the core AutonomousEngineeringLoop policy that
    Qwen is not an autonomous coding/generation provider after repeated bounded
    timeout failures. Normal edit limits, tests, Security, review, validation,
    provenance, and promotion gates still apply.
    """
    candidates = []
    for provider in self.providers.available_providers():
        if _is_qwen(provider):
            continue
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
                float(profile.resource_cost),
                profile.name,
                provider,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:3])
    return candidates[0][3]


def _task_payload_and_finding(task) -> tuple[dict, dict]:
    payload = getattr(task, "payload", {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    finding = payload.get("finding")
    discovery = payload.get("discovery")
    if not isinstance(finding, dict) and isinstance(discovery, dict):
        finding = discovery.get("finding")
    if not isinstance(finding, dict):
        finding = {}
    return payload, finding


def _is_new_capability_task(task) -> bool:
    payload, finding = _task_payload_and_finding(task)
    target = str(payload.get("target_path") or "").replace("\\", "/").lstrip("./")
    task_type = str(payload.get("task_type") or "").strip().lower()
    return (
        target == LEARNED_CAPABILITY_TARGET
        or task_type == "new_capability"
        or finding.get("new_capability") is True
    )


def _is_grounded_agentic_capability_task(task) -> bool:
    """Allow model synthesis only for evidence-backed learned-capability work."""
    payload, finding = _task_payload_and_finding(task)
    target = str(payload.get("target_path") or "").replace("\\", "/").lstrip("./")
    source = str(payload.get("source") or "").strip()
    lesson = str(finding.get("lesson") or finding.get("summary") or "").strip()
    evidence = str(
        finding.get("lesson_evidence")
        or finding.get("learning_evidence")
        or finding.get("evidence")
        or ""
    ).strip()
    return (
        target == LEARNED_CAPABILITY_TARGET
        and source == "genesis.evolution_learning"
        and finding.get("new_capability") is True
        and finding.get("grounded") is True
        and bool(lesson)
        and bool(evidence)
    )


def _install_scoped_capability_guards(self: AutonomousEngineeringLoop, task):
    """Restrict agentic capability synthesis to append-only incubator insertion."""
    original_context = self._context_paths_for_task
    original_validate = self.coding.validate_proposal
    task_id = str(getattr(task, "task_id", ""))

    def scoped_context(_self, candidate_task):
        if str(getattr(candidate_task, "task_id", "")) == task_id:
            target = self.root / LEARNED_CAPABILITY_TARGET
            return [LEARNED_CAPABILITY_TARGET] if target.is_file() else []
        return original_context(candidate_task)

    def scoped_validate(_coding, proposal, provider_name):
        validated = original_validate(proposal, provider_name)
        if set(validated.files) != {LEARNED_CAPABILITY_TARGET}:
            raise ValueError("agentic new capability may edit only the learned capability incubator")

        target = self.root / LEARNED_CAPABILITY_TARGET
        current = target.read_text(encoding="utf-8")
        proposed = validated.files[LEARNED_CAPABILITY_TARGET]
        if current.count(LEARNED_CAPABILITY_MARKER) != 1:
            raise ValueError("learned capability insertion marker is missing or ambiguous")
        if proposed.count(LEARNED_CAPABILITY_MARKER) != 1:
            raise ValueError("agentic capability proposal must preserve the insertion marker exactly once")

        prefix, suffix = current.split(LEARNED_CAPABILITY_MARKER, 1)
        tail = LEARNED_CAPABILITY_MARKER + suffix
        if not proposed.startswith(prefix) or not proposed.endswith(tail):
            raise ValueError("agentic capability proposal must be append-only before the insertion marker")
        insertion_end = len(proposed) - len(tail)
        inserted = proposed[len(prefix):insertion_end]
        if not inserted.strip():
            raise ValueError("agentic capability proposal contains no new implementation")
        if LEARNED_CAPABILITY_MARKER in inserted:
            raise ValueError("agentic capability proposal may not duplicate the insertion marker")
        if len(inserted.encode("utf-8")) > self.coding.MAX_EDIT_BYTES:
            raise ValueError("agentic capability insertion exceeds bounded edit size")
        return validated

    had_context_override = "_context_paths_for_task" in self.__dict__
    previous_context_override = self.__dict__.get("_context_paths_for_task")
    had_validate_override = "validate_proposal" in self.coding.__dict__
    previous_validate_override = self.coding.__dict__.get("validate_proposal")
    self._context_paths_for_task = MethodType(scoped_context, self)
    self.coding.validate_proposal = MethodType(scoped_validate, self.coding)

    def restore() -> None:
        if had_context_override:
            self.__dict__["_context_paths_for_task"] = previous_context_override
        else:
            self.__dict__.pop("_context_paths_for_task", None)
        if had_validate_override:
            self.coding.__dict__["validate_proposal"] = previous_validate_override
        else:
            self.coding.__dict__.pop("validate_proposal", None)

    return restore


def _attempt_task_with_provider_fallback(self: AutonomousEngineeringLoop, task, runtime):
    """Use the best eligible non-Qwen provider while keeping creation bounded."""
    if not _is_new_capability_task(task):
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        result["provider_policy"] = "qwen_excluded_from_coding"
        return result

    if _is_grounded_agentic_capability_task(task):
        restore = _install_scoped_capability_guards(self, task)
        try:
            result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        finally:
            restore()
        result["provider_policy"] = "grounded_agentic_capability_non_qwen_only"
        result["capability_scope"] = "append_only_learned_capability"
        if result.get("coding_strategy") == "external_non_qwen_provider":
            result["coding_strategy"] = "agentic_grounded_capability_provider"
        return result

    # Ungrounded capability invention remains blocked. Genesis may reason about the
    # gap, but implementation requires evidence strong enough to enter the grounded
    # evolution-learning lane or a stronger non-Qwen provider.
    had_override = "_coding_provider" in self.__dict__
    previous_override = self.__dict__.get("_coding_provider")
    self._coding_provider = MethodType(_ORIGINAL_CODING_PROVIDER, self)
    try:
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        result["provider_policy"] = "ungrounded_capability_requires_stronger_provider"
        return result
    finally:
        if had_override:
            self.__dict__["_coding_provider"] = previous_override
        else:
            self.__dict__.pop("_coding_provider", None)


def install_provider_fallback() -> None:
    """Install capability-driven provider selection once for every Genesis entrypoint."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._coding_provider = _select_eligible_coding_provider
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_provider_fallback
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)
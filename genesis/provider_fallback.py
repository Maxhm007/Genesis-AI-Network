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
    """Choose the best available bounded model coding provider.

    Qwen is the preferred cognitive ancestor for Genesis when it is available and
    capable. Other non-bootstrap providers remain valid fallbacks. Selection does
    not weaken edit limits, tests, Security, review, independent validation,
    provenance, signed quorum, or promotion gates.
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
                0 if _is_qwen(provider) else 1,
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


def _marker_replacement(text: str) -> str:
    stripped = str(text).rstrip("\n")
    if not stripped.strip():
        return stripped
    return stripped + "\n\n" + LEARNED_CAPABILITY_MARKER


def _normalize_learned_capability_proposal(proposal: dict, current: str) -> dict:
    """Repair only the mechanical marker preservation for a scoped insertion.

    The model still owns the implementation text. Genesis locally preserves the
    single trusted insertion marker when the proposal clearly replaces that marker
    or supplies an otherwise append-only full-file candidate. No unrelated edit is
    widened or rewritten, and the normal syntax/scope/size validation still runs.
    """
    if not isinstance(proposal, dict) or current.count(LEARNED_CAPABILITY_MARKER) != 1:
        return proposal

    normalized = dict(proposal)
    prefix, suffix = current.split(LEARNED_CAPABILITY_MARKER, 1)
    marker_line = current[: current.index(LEARNED_CAPABILITY_MARKER)].count("\n") + 1

    edits = proposal.get("edits")
    if isinstance(edits, list) and len(edits) == 1 and isinstance(edits[0], dict):
        edit = dict(edits[0])
        path = str(edit.get("path") or "").replace("\\", "/").lstrip("./")
        replacement = edit.get("new")
        if path == LEARNED_CAPABILITY_TARGET and isinstance(replacement, str):
            try:
                start_line = int(edit.get("start_line"))
                end_line = int(edit.get("end_line"))
            except Exception:
                start_line = end_line = -1
            old = edit.get("old")
            replaces_marker = bool(
                (start_line == marker_line and end_line == marker_line)
                or str(old or "").strip() == LEARNED_CAPABILITY_MARKER
            )
            if replaces_marker and replacement.count(LEARNED_CAPABILITY_MARKER) == 0:
                edit["new"] = _marker_replacement(replacement)
                normalized["edits"] = [edit]

    files = proposal.get("files")
    if isinstance(files, dict) and set(files) == {LEARNED_CAPABILITY_TARGET}:
        proposed = files.get(LEARNED_CAPABILITY_TARGET)
        if isinstance(proposed, str) and proposed.count(LEARNED_CAPABILITY_MARKER) == 0:
            append_only_shape = proposed.startswith(prefix)
            if suffix:
                append_only_shape = append_only_shape and proposed.endswith(suffix)
            if append_only_shape:
                insertion_end = len(proposed) - len(suffix) if suffix else len(proposed)
                insertion = proposed[len(prefix):insertion_end]
                if insertion.strip():
                    repaired = prefix + insertion.rstrip("\n") + "\n\n" + LEARNED_CAPABILITY_MARKER + suffix
                    normalized["files"] = {LEARNED_CAPABILITY_TARGET: repaired}

    return normalized


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
        target = self.root / LEARNED_CAPABILITY_TARGET
        current = target.read_text(encoding="utf-8")
        normalized = _normalize_learned_capability_proposal(proposal, current)
        validated = original_validate(normalized, provider_name)
        if set(validated.files) != {LEARNED_CAPABILITY_TARGET}:
            raise ValueError("agentic new capability may edit only the learned capability incubator")

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
    """Use Qwen-first cognitive coding while keeping all execution gates bounded."""
    if not _is_new_capability_task(task):
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        result["provider_policy"] = "qwen_preferred_cognitive_coding"
        return result

    if _is_grounded_agentic_capability_task(task):
        restore = _install_scoped_capability_guards(self, task)
        try:
            result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        finally:
            restore()
        result["provider_policy"] = "grounded_agentic_capability_qwen_preferred"
        result["capability_scope"] = "append_only_learned_capability"
        if result.get("coding_strategy") == "external_non_qwen_provider":
            result["coding_strategy"] = "agentic_grounded_capability_provider"
        return result

    # Ungrounded capability invention remains blocked from the scoped learned-
    # capability lane. Qwen can reason about the gap elsewhere, but autonomous
    # implementation still requires grounded evidence or an explicitly supported
    # ordinary engineering task.
    had_override = "_coding_provider" in self.__dict__
    previous_override = self.__dict__.get("_coding_provider")
    self._coding_provider = MethodType(_ORIGINAL_CODING_PROVIDER, self)
    try:
        result = _ORIGINAL_ATTEMPT_TASK(self, task, runtime)
        result["provider_policy"] = "ungrounded_capability_requires_grounded_evidence"
        return result
    finally:
        if had_override:
            self.__dict__["_coding_provider"] = previous_override
        else:
            self.__dict__.pop("_coding_provider", None)


def install_provider_fallback() -> None:
    """Install Qwen-first capability-driven provider selection once."""
    if getattr(AutonomousEngineeringLoop, INSTALL_MARKER, False):
        return
    AutonomousEngineeringLoop._coding_provider = _select_eligible_coding_provider
    AutonomousEngineeringLoop._attempt_task = _attempt_task_with_provider_fallback
    setattr(AutonomousEngineeringLoop, INSTALL_MARKER, True)

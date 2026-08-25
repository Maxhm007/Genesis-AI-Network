from __future__ import annotations

import re
from pathlib import Path

from .autonomous_engineering import AutonomousEngineeringLoop
from .coding import CodingModule
from .intelligence_router import IntelligenceRouter
from .providers import GenesisHTTPProvider


INSTALL_MARKER = "_genesis_coding_provider_policy_installed"
CODING_ROLE = "bounded_coding_engineer"
TRANSPORT_CODING_ROLE = "bounded_coding_engineer_full_budget"
MAX_BOUNDED_EDITS = 2
MAX_GROUNDED_CONTEXT_FILES = 6
MAX_GROUNDING_SOURCE_CHARS = 4_000
_ORIGINAL_HTTP_REASON = GenesisHTTPProvider.reason
_ORIGINAL_CODING_PROPOSE = CodingModule.propose

ISSUE_EVIDENCE_MARKER = "ISSUE_EVIDENCE:"
REQUEST_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(?:required(?:\s+system)?\s+improvement|requirements?|acceptance(?:\s+criteria)?|expected(?:\s+behavior)?|requested\s+change|remediation|fix)\s*:?\s*$"
)
EXPLICIT_GENESIS_PATH_RE = re.compile(r"(?:^|[\s`'\"(])((?:genesis)/[A-Za-z0-9_./-]+\.py)")
GROUNDING_STOPWORDS = {
    "about",
    "after",
    "before",
    "could",
    "does",
    "from",
    "have",
    "into",
    "issue",
    "should",
    "that",
    "their",
    "there",
    "these",
    "this",
    "when",
    "where",
    "which",
    "with",
}
GROUNDING_EXCLUDED = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/issue_solver.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
}


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


def _grounding_tokens(text: str) -> set[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", str(text))
    }
    return {token for token in tokens if token not in GROUNDING_STOPWORDS}


def _request_focus_text(issue_evidence: str) -> str:
    """Prefer the requested outcome over historical examples in an issue body."""
    text = str(issue_evidence)
    title = ""
    for line in text.splitlines()[:4]:
        if line.startswith("TITLE:"):
            title = line
            break
    match = REQUEST_HEADING_RE.search(text)
    if match is None:
        return text
    tail = text[match.start() :]
    return (title + "\n" + tail).strip() if title else tail


def _explicit_focus_paths(text: str) -> list[str]:
    rows: list[str] = []
    for raw in EXPLICIT_GENESIS_PATH_RE.findall(text):
        normalized = raw.replace("\\", "/").lstrip("./")
        if ".." in Path(normalized).parts or normalized in GROUNDING_EXCLUDED:
            continue
        if normalized not in rows:
            rows.append(normalized)
    return rows


def _safe_grounding_source(module: CodingModule, relative: str) -> str | None:
    normalized = str(relative).replace("\\", "/").lstrip("./")
    if normalized in GROUNDING_EXCLUDED or normalized.endswith("/__init__.py"):
        return None
    try:
        target = module._validate_path(normalized)
    except Exception:
        return None
    if not target.is_file() or target.suffix != ".py" or not normalized.startswith("genesis/"):
        return None
    try:
        return target.read_text(encoding="utf-8", errors="ignore")[:MAX_GROUNDING_SOURCE_CHARS]
    except OSError:
        return None


def _ground_issue_context_paths(
    module: CodingModule,
    objective: str,
    context_paths: list[str] | None,
) -> list[str]:
    """Re-rank issue context from requested behavior rather than evidence examples.

    GitHub issue bodies often mention a file that was involved in the historical
    failure. An explicit path in that evidence must not automatically become the
    repair target when a later Requirements/Acceptance/Fix section asks for a
    system-level improvement. Explicit paths inside the requested-outcome section
    still receive strongest priority.
    """
    current = [str(path).replace("\\", "/").lstrip("./") for path in (context_paths or [])]
    if ISSUE_EVIDENCE_MARKER not in objective:
        return current

    issue_evidence = objective.split(ISSUE_EVIDENCE_MARKER, 1)[1]
    focus = _request_focus_text(issue_evidence)
    focus_tokens = _grounding_tokens(focus)
    explicit_focus = _explicit_focus_paths(focus)

    scored: list[tuple[int, int, str]] = []
    genesis_dir = module.root / "genesis"
    if genesis_dir.is_dir():
        for path in genesis_dir.rglob("*.py"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(module.root).as_posix()
            source = _safe_grounding_source(module, relative)
            if source is None:
                continue
            path_overlap = len(focus_tokens & _grounding_tokens(relative))
            source_overlap = len(focus_tokens & _grounding_tokens(source))
            explicit_bonus = 100 if relative in explicit_focus else 0
            score = explicit_bonus + path_overlap * 8 + source_overlap
            scored.append((score, path.stat().st_size, relative))

    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    positive = [relative for score, _, relative in scored if score > 0]
    if not positive:
        return current

    bounded = positive[:MAX_GROUNDED_CONTEXT_FILES]
    # Mutate the caller-owned list so the GitHub autorepair scope check uses the
    # same grounded paths that the coding provider actually saw.
    if context_paths is not None:
        context_paths[:] = bounded
    return bounded


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

    grounded_paths = _ground_issue_context_paths(self, objective, context_paths)
    had_override = "MAX_EDITS" in self.__dict__
    previous_override = self.__dict__.get("MAX_EDITS")
    self.MAX_EDITS = MAX_BOUNDED_EDITS
    try:
        return _ORIGINAL_CODING_PROPOSE(self, objective, grounded_paths, provider=selected)
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

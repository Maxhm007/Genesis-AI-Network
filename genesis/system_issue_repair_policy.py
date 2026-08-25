from __future__ import annotations

import re
from pathlib import Path

from . import coding_provider_policy as coding_policy
from . import selfdev as selfdev_module
from .coding import CodingModule
from .selfdev import SelfDevelopmentExecutor


INSTALL_MARKER = "_genesis_system_issue_repair_policy_installed"
PRIVILEGE_ANCHOR = ".github/workflows/github-issue-autorepair.yml"
MAX_CONTEXT_FILES = 6
EXPLICIT_REPAIR_PATH_RE = re.compile(
    r"(?:^|[\s`'\"(])((?:genesis|scripts)/[A-Za-z0-9_./-]+\.py)"
)
PROTECTED_SYSTEM_REPAIR_PATHS = {
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}

_ORIGINAL_GROUND = coding_policy._ground_issue_context_paths
_ORIGINAL_NORMALIZE = selfdev_module.normalize_selfdev_path
_ORIGINAL_EXECUTE = SelfDevelopmentExecutor.execute


def _explicit_focus_paths(text: str) -> list[str]:
    rows: list[str] = []
    for raw in EXPLICIT_REPAIR_PATH_RE.findall(str(text)):
        normalized = raw.replace("\\", "/").lstrip("./")
        if (
            ".." in Path(normalized).parts
            or normalized in coding_policy.GROUNDING_EXCLUDED
            or normalized in PROTECTED_SYSTEM_REPAIR_PATHS
        ):
            continue
        if normalized not in rows:
            rows.append(normalized)
    return rows


def _safe_source(module: CodingModule, relative: str) -> str | None:
    normalized = str(relative).replace("\\", "/").lstrip("./")
    if not normalized.startswith(("genesis/", "scripts/")):
        return None
    if (
        normalized in coding_policy.GROUNDING_EXCLUDED
        or normalized in PROTECTED_SYSTEM_REPAIR_PATHS
        or normalized.endswith("/__init__.py")
        or ".." in Path(normalized).parts
    ):
        return None
    root = module.root.resolve()
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file() or target.suffix != ".py":
        return None
    try:
        return target.read_text(encoding="utf-8", errors="ignore")[: coding_policy.MAX_GROUNDING_SOURCE_CHARS]
    except OSError:
        return None


def _companion_test(root: Path, source: str) -> str | None:
    source_path = Path(source)
    candidate = f"tests/test_{source_path.stem}.py"
    return candidate if (root / candidate).is_file() else None


def _ground_requested_issue_context(
    module: CodingModule,
    objective: str,
    context_paths: list[str] | None,
) -> list[str]:
    """Ground GitHub issue repair in the requested outcome, including safe scripts.

    The ordinary coding policy can only rank ``genesis/*.py``. System-level issue
    defects often live in bounded ``scripts/*.py`` control-plane helpers, so a
    historical application-file mention must not trap repair there forever. Safe
    script targets remain privileged-only at execution time.
    """
    current = [str(path).replace("\\", "/").lstrip("./") for path in (context_paths or [])]
    if coding_policy.ISSUE_EVIDENCE_MARKER not in objective:
        return current

    issue_evidence = objective.split(coding_policy.ISSUE_EVIDENCE_MARKER, 1)[1]
    focus = coding_policy._request_focus_text(issue_evidence)
    focus_tokens = coding_policy._grounding_tokens(focus)
    explicit_focus = _explicit_focus_paths(focus)

    scored: list[tuple[int, int, str]] = []
    for directory in (module.root / "genesis", module.root / "scripts"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(module.root).as_posix()
            source = _safe_source(module, relative)
            if source is None:
                continue
            path_overlap = len(focus_tokens & coding_policy._grounding_tokens(relative))
            source_overlap = len(focus_tokens & coding_policy._grounding_tokens(source))
            explicit_bonus = 200 if relative in explicit_focus else 0
            script_bonus = 4 if relative.startswith("scripts/") and "autorepair" in focus_tokens else 0
            score = explicit_bonus + path_overlap * 12 + source_overlap + script_bonus
            scored.append((score, path.stat().st_size, relative))

    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    positive = [relative for score, _, relative in scored if score > 0]
    if not positive:
        return _ORIGINAL_GROUND(module, objective, context_paths)

    bounded: list[str] = []
    for source in positive:
        if source not in bounded:
            bounded.append(source)
        companion = _companion_test(module.root, source)
        if companion and companion not in bounded:
            bounded.append(companion)
        if len(bounded) >= MAX_CONTEXT_FILES:
            break
    bounded = bounded[:MAX_CONTEXT_FILES]
    if context_paths is not None:
        context_paths[:] = bounded
    return bounded


def _normalize_with_privileged_scripts(
    root: Path,
    path: str,
    *,
    allow_privileged: bool = False,
) -> str:
    normalized = str(path).replace("\\", "/").lstrip("./")
    if normalized.startswith("scripts/") and not allow_privileged:
        raise RuntimeError("script changes require the privileged autonomy lane")
    return _ORIGINAL_NORMALIZE(root, path, allow_privileged=allow_privileged)


def _proposal_with_privilege_anchor(executor: SelfDevelopmentExecutor, proposal: dict | None) -> dict | None:
    if proposal is None:
        return None
    raw_files = dict(proposal.get("files", {}))
    if not any(str(path).replace("\\", "/").lstrip("./").startswith("scripts/") for path in raw_files):
        return proposal
    anchor = executor.root / PRIVILEGE_ANCHOR
    if not anchor.is_file():
        raise RuntimeError("privileged issue-repair anchor is unavailable")
    value = dict(proposal)
    files = dict(raw_files)
    files.setdefault(PRIVILEGE_ANCHOR, anchor.read_text(encoding="utf-8"))
    value["files"] = files
    return value


def _execute_with_privileged_system_issue_lane(
    self: SelfDevelopmentExecutor,
    proposal: dict | None = None,
):
    return _ORIGINAL_EXECUTE(self, _proposal_with_privilege_anchor(self, proposal))


def install_system_issue_repair_policy() -> None:
    """Install privileged script repair without widening the normal sandbox."""
    if getattr(SelfDevelopmentExecutor, INSTALL_MARKER, False):
        return

    if "scripts/" not in selfdev_module.ALLOWED_PREFIXES:
        selfdev_module.ALLOWED_PREFIXES = (*selfdev_module.ALLOWED_PREFIXES, "scripts/")
    selfdev_module.normalize_selfdev_path = _normalize_with_privileged_scripts
    coding_policy._ground_issue_context_paths = _ground_requested_issue_context
    SelfDevelopmentExecutor.execute = _execute_with_privileged_system_issue_lane
    setattr(SelfDevelopmentExecutor, INSTALL_MARKER, True)

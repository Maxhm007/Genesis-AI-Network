from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import scripts.github_issue_autorepair as base
from genesis.selfdev import ALLOWED_SCRIPT_PATHS, normalize_selfdev_path


STRATEGY_GUIDANCE = {
    "evidence_first": (
        "Agentic Lab strategy: evidence-first current-state verification. Before proposing ANY edit, inspect current main, "
        "the Issue acceptance criteria, preserved repair memory, and existing focused/regression tests. First decide whether "
        "the objective is already satisfied on current main. If it is already satisfied, do not invent or replay a patch; "
        "preserve evidence that the current implementation and tests satisfy the Issue so orchestration can treat the Issue "
        "as stale/already complete. Only when a concrete remaining gap is demonstrated may you edit, and then prefer the "
        "smallest change that directly addresses that observed gap. Never repeat a rejected candidate merely because the Issue is open."
    ),
    "alternative_implementation": (
        "Agentic Lab strategy: alternative implementation. The prior method failed. Re-check current main and the remaining "
        "acceptance gap first. If the Issue is already satisfied, do not edit. Otherwise use a materially different implementation "
        "path while keeping the same acceptance criteria and exact target scope. Do not reproduce the same control flow, helper "
        "shape, or rejected patch with cosmetic changes."
    ),
    "diagnostic_reframe": (
        "Agentic Lab strategy: diagnostic reframe. Re-check current main before editing. Re-evaluate whether the apparent target "
        "defect is already fixed or is caused by an adjacent invariant, data shape, state transition, or integration assumption "
        "visible in the allowed repository context. Then implement the smallest safe target-local correction only if a real remaining "
        "gap is demonstrated."
    ),
    "dependency_diagnosis": (
        "Agentic Lab strategy: dependency diagnosis. Re-check current main before assuming a dependency. Determine whether the "
        "remaining blocker is lack of a Genesis repair capability, provider/tooling limitation, unavailable dependency, insufficient "
        "safe context, or an Issue whose objective is already satisfied. If a reusable repair capability is genuinely missing, the "
        "orchestration layer will open a capability-building dependency issue. If a safe target-local repair is still necessary, implement "
        "it. Otherwise return without inventing a change."
    ),
    "qwen3_fallback": (
        "Agentic Lab final fallback strategy using the isolated Qwen3 provider. All earlier Agentic strategies already failed on this "
        "same Issue. Read their comments as repair memory, re-check current main and acceptance criteria, and attempt a genuinely new "
        "bounded solution. Do not bypass scope, protected-file, validation, security, promotion, or verify-before-close gates. If no "
        "verified solution can be produced, return failure evidence only; the Issue must remain open and authoritative."
    ),
}

CAPABILITY_LIKE_REASONS = {
    "retry_pending_capability",
    "blocked_no_safe_context",
    "blocked_protected_or_unsupported_target",
}

PROTECTED_SCRIPT_TARGETS = {
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}

_SCRIPT_TARGET_RE = re.compile(r"(?:^|[\s`'\"(])(scripts/[A-Za-z0-9_./-]+\.py)")


def _explicit_safe_script_paths(issue_text: str, root: Path) -> list[str]:
    rows: list[str] = []
    for raw in _SCRIPT_TARGET_RE.findall(issue_text):
        normalized = raw.replace("\\", "/").removeprefix("./")
        if normalized not in ALLOWED_SCRIPT_PATHS or normalized in PROTECTED_SCRIPT_TARGETS:
            continue
        try:
            normalize_selfdev_path(root, normalized)
        except RuntimeError:
            continue
        if (root / normalized).is_file() and normalized not in rows:
            rows.append(normalized)
    return rows


def _script_aware_context_paths(original, issue_text: str, root: Path, limit: int) -> list[str]:
    explicit_scripts = _explicit_safe_script_paths(issue_text, root)
    if explicit_scripts:
        return explicit_scripts[: max(1, min(int(limit), base.MAX_CONTEXT_FILES))]
    return original(issue_text, root, limit)


def _script_aware_allowed_paths(original, context_paths: list[str]) -> set[str]:
    allowed = set(original(context_paths))
    for relative in context_paths:
        path = Path(relative)
        if relative in ALLOWED_SCRIPT_PATHS and relative not in PROTECTED_SCRIPT_TARGETS:
            allowed.add(f"tests/test_{path.stem}.py")
    return allowed


def _navigation_landmark_micro_repair(issue: dict, context_paths: list[str], root: Path):
    issue_text = base.build_issue_text(issue)
    lowered = issue_text.lower()
    if "navigation landmark" not in lowered or "aria-label" not in lowered:
        return None
    if len(context_paths) != 1:
        return None
    target = context_paths[0]
    if target not in ALLOWED_SCRIPT_PATHS or target in PROTECTED_SCRIPT_TARGETS:
        return None
    try:
        normalize_selfdev_path(root, target)
    except RuntimeError:
        return None
    path = root / target
    if not path.is_file():
        return None
    current = path.read_text(encoding="utf-8")
    desired = '<nav class="nav" aria-label="Dashboard navigation">'
    if desired in current:
        return None
    insertion = '    html = DASHBOARD.read_text(encoding="utf-8")\n'
    if current.count(insertion) != 1:
        return None
    repair = insertion + '    html = html.replace(\'<nav class="nav">\', \'<nav class="nav" aria-label="Dashboard navigation">\', 1)\n'
    proposed = current.replace(insertion, repair, 1)
    return base.CodingProposal(
        title="Label dashboard navigation landmark",
        rationale="Deterministic micro-repair for an explicitly evidenced missing navigation aria-label.",
        files={target: proposed},
        provider="genesis-agentic-micro-repair",
    )


def _micro_repair_or_original(original, issue: dict, context_paths: list[str], root: Path = base.ROOT, **kwargs):
    micro = _navigation_landmark_micro_repair(issue, context_paths, root)
    if micro is not None:
        return micro
    return original(issue, context_paths, root, **kwargs)


def run(issue_number: int, repository: str, strategy: str) -> dict:
    if strategy not in STRATEGY_GUIDANCE:
        raise ValueError(f"unsupported Agentic Lab strategy: {strategy}")
    original_loader = base.load_maintainer_repair_guidance
    original_context_paths = base.candidate_context_paths
    original_allowed_paths = base.allowed_issue_repair_paths
    original_propose = base.propose_issue_repair
    existing_guidance = original_loader(repository, issue_number)
    strategy_guidance = STRATEGY_GUIDANCE[strategy]

    def load_guidance(_repository: str, _issue_number: int) -> str:
        combined = "\n\n".join(piece for piece in (existing_guidance, strategy_guidance) if piece.strip())
        return combined[: base.MAX_MAINTAINER_GUIDANCE_CHARS]

    def context_paths(issue_text: str, root: Path = base.ROOT, limit: int = base.MAX_CONTEXT_FILES) -> list[str]:
        return _script_aware_context_paths(original_context_paths, issue_text, root, limit)

    def allowed_paths(paths: list[str]) -> set[str]:
        return _script_aware_allowed_paths(original_allowed_paths, paths)

    def propose(issue: dict, paths: list[str], root: Path = base.ROOT, **kwargs):
        return _micro_repair_or_original(original_propose, issue, paths, root, **kwargs)

    base.load_maintainer_repair_guidance = load_guidance
    base.candidate_context_paths = context_paths
    base.allowed_issue_repair_paths = allowed_paths
    base.propose_issue_repair = propose
    try:
        evidence = base.run(issue_number, repository)
    finally:
        base.load_maintainer_repair_guidance = original_loader
        base.candidate_context_paths = original_context_paths
        base.allowed_issue_repair_paths = original_allowed_paths
        base.propose_issue_repair = original_propose

    evidence["agentic_strategy"] = strategy
    evidence["current_state_checked_first"] = True
    reason = str(evidence.get("reason") or evidence.get("repair_status") or "").strip()
    if strategy not in {"dependency_diagnosis", "qwen3_fallback"} and reason in CAPABILITY_LIKE_REASONS:
        evidence["prior_capability_signal"] = reason
        evidence["reason"] = "strategy_requires_more_methods"
        evidence["status"] = "retry_pending"
    base.EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Agentic Lab repair strategy")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--strategy", choices=tuple(STRATEGY_GUIDANCE), required=True)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    print(json.dumps(run(args.issue_number, args.repository, args.strategy), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

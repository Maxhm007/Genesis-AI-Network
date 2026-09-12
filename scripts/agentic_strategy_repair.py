from __future__ import annotations

import argparse
import json
import os

import scripts.github_issue_autorepair as base


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
        "safe context, or an Issue whose objective is already satisfied. If a safe target-local repair is still necessary, implement "
        "it. Otherwise return without inventing a change; when a real capability gap remains, the orchestration layer will open a capability-building dependency issue."
    ),
}

CAPABILITY_LIKE_REASONS = {
    "retry_pending_capability",
    "blocked_no_safe_context",
    "blocked_protected_or_unsupported_target",
}


def run(issue_number: int, repository: str, strategy: str) -> dict:
    if strategy not in STRATEGY_GUIDANCE:
        raise ValueError(f"unsupported Agentic Lab strategy: {strategy}")

    original_loader = base.load_maintainer_repair_guidance
    existing_guidance = original_loader(repository, issue_number)
    strategy_guidance = STRATEGY_GUIDANCE[strategy]

    def load_guidance(_repository: str, _issue_number: int) -> str:
        combined = "\n\n".join(piece for piece in (existing_guidance, strategy_guidance) if piece.strip())
        return combined[: base.MAX_MAINTAINER_GUIDANCE_CHARS]

    base.load_maintainer_repair_guidance = load_guidance
    try:
        evidence = base.run(issue_number, repository)
    finally:
        base.load_maintainer_repair_guidance = original_loader

    evidence["agentic_strategy"] = strategy
    evidence["current_state_checked_first"] = True
    reason = str(evidence.get("reason") or evidence.get("repair_status") or "").strip()
    if strategy != "dependency_diagnosis" and reason in CAPABILITY_LIKE_REASONS:
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

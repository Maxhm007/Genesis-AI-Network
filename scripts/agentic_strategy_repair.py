from __future__ import annotations

import argparse
import json
import os

import scripts.github_issue_autorepair as base


STRATEGY_GUIDANCE = {
    "evidence_first": (
        "Agentic Lab strategy: evidence-first. Diagnose the exact prior rejection, validation failure, or missing behavior before editing. "
        "Use the preserved repair memory as evidence. Do not repeat the previous candidate. Prefer the smallest change that directly addresses the observed failure."
    ),
    "alternative_implementation": (
        "Agentic Lab strategy: alternative implementation. The prior method failed. Use a materially different implementation path while keeping the same acceptance criteria and exact target scope. "
        "Do not reproduce the same control flow, helper shape, or rejected patch with cosmetic changes."
    ),
    "diagnostic_reframe": (
        "Agentic Lab strategy: diagnostic reframe. Re-evaluate whether the apparent target defect is caused by an adjacent invariant, data shape, state transition, or integration assumption visible in the allowed repository context. "
        "Then implement the smallest safe target-local correction supported by that diagnosis."
    ),
    "dependency_diagnosis": (
        "Agentic Lab strategy: dependency diagnosis. Determine whether the remaining blocker is lack of a Genesis repair capability, provider/tooling limitation, unavailable dependency, or insufficient safe context. "
        "If a safe target-local repair is still possible, implement it. Otherwise return without inventing a change; the orchestration layer will open a capability-building dependency issue."
    ),
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

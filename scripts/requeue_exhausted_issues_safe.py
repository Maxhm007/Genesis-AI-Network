from __future__ import annotations

"""Safety wrapper for exhausted-Issue requeueing.

The legacy requeue engine can legitimately reopen Issues that were closed only as
an unresolved/deferred exhaustion state. It must never resurrect Issues that are
actually completed, verified, duplicate, superseded, or otherwise intentionally
closed.
"""

from pathlib import Path

import requeue_exhausted_issues as core


PROTECTED_CLOSED_LABELS = {
    "genesis-verified",
    "genesis-solved",
    "genesis-superseded",
}

_ORIGINAL_ELIGIBLE = core.eligible_exhausted_issue
_ORIGINAL_HANDOFF = core.handoff_exhausted_to_agentic_lab


def closed_reactivation_allowed(issue: dict) -> tuple[bool, str]:
    """Return whether a closed Issue is allowed to be reopened for repair.

    Only unresolved exhaustion closures are eligible: GitHub state_reason must be
    ``not_planned`` and the Issue must still carry ``genesis-deferred``. Any
    verified/solved/superseded signal is terminal and blocks resurrection.
    """

    if str(issue.get("state") or "open").lower() != "closed":
        return True, "open"

    labels = core.issue_labels(issue)
    protected = labels & PROTECTED_CLOSED_LABELS
    if protected:
        return False, "terminal_closed"

    state_reason = str(issue.get("state_reason") or "").lower()
    if state_reason != "not_planned":
        return False, "terminal_closed"
    if "genesis-deferred" not in labels:
        return False, "intentional_closed"
    if not labels & core.EXHAUSTED_LABELS:
        return False, "not_exhausted"
    return True, "deferred_exhaustion"


def safe_eligible_exhausted_issue(issue: dict, root: Path = core.ROOT) -> tuple[bool, str]:
    allowed, reason = closed_reactivation_allowed(issue)
    if not allowed:
        return False, reason
    return _ORIGINAL_ELIGIBLE(issue, root)


def safe_handoff_exhausted_to_agentic_lab(
    repository: str,
    token: str,
    issue: dict,
    comments: list[dict],
) -> dict:
    allowed, reason = closed_reactivation_allowed(issue)
    if not allowed:
        raise RuntimeError(f"closed Issue is not eligible for reactivation: {reason}")
    return _ORIGINAL_HANDOFF(repository, token, issue, comments)


def main() -> None:
    core.eligible_exhausted_issue = safe_eligible_exhausted_issue
    core.handoff_exhausted_to_agentic_lab = safe_handoff_exhausted_to_agentic_lab
    core.main()


if __name__ == "__main__":
    main()

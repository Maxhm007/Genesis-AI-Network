from __future__ import annotations

from .file_self_review import FileSelfReviewLoop, REVIEW_METHODS


class QuorumFileSelfReviewLoop(FileSelfReviewLoop):
    """Add bounded independent-method confirmation before accepting no-change.

    A single reasoning pass must not be able to mark a source file complete just
        if len(confirmations) < self.NO_CHANGE_QUORUM:
            current["no_change_confirmations"] = confirmations
            current["status"] = "retry"
            current["method_index"] = (int(current.get("method_index", 0)) + 1) % len(REVIEW_METHODS)
            current["last_error"] = "no-change requires confirmation by a second independent review method"
            state["current"] = current
            self._save(state)
            return
    rotates to a different review method, and advances only after two distinct
    methods independently agree that no meaningful improvement is justified.

    Improvement findings, protected-file escalation, candidate validation,
    promotion confirmation, and retry behavior continue to use the base loop.
    """

    NO_CHANGE_QUORUM = 2

    def _advance(self, state: dict, outcome: dict) -> None:
        if outcome.get("status") != "reviewed_no_change":
            super()._advance(state, outcome)
            return

        current = state.get("current") or {}
        method = str(outcome.get("method") or "")
        confirmations = list(current.get("no_change_confirmations", []) or [])
        if method and not any(item.get("method") == method for item in confirmations):
            confirmations.append(
                {
                    "method": method,
                    "summary": outcome.get("summary"),
                    "confidence": outcome.get("confidence"),
                    "reviewed_at": outcome.get("reviewed_at"),
                }
            )

        if len(confirmations) < self.NO_CHANGE_QUORUM:
            current["no_change_confirmations"] = confirmations
            current["status"] = "retry"
            current["method_index"] = (int(current.get("method_index", 0)) + 1) % len(REVIEW_METHODS)
            current["last_error"] = "no-change requires confirmation by a second independent review method"
            state["current"] = current
            self._save(state)
            return

        outcome = dict(outcome)
        outcome["confirmation_count"] = len(confirmations)
        outcome["confirmation_methods"] = [item.get("method") for item in confirmations]
        outcome["confirmations"] = confirmations
        super()._advance(state, outcome)

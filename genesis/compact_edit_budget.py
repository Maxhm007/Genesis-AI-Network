from __future__ import annotations

from .coding import CodingModule


INSTALL_MARKER = "_genesis_compact_edit_materialization_budget_installed"
_ORIGINAL_VALIDATE_PROPOSAL = CodingModule.validate_proposal


def _validate_proposal_with_compact_edit_materialization_budget(
    self: CodingModule,
    proposal: dict,
    provider_name: str,
):
    """Keep provider byte limits strict without charging compact edits for existing source.

    ``MAX_TOTAL_BYTES`` protects the full-file proposal protocol from oversized model
    output. A compact edit is independently bounded by ``MAX_EDITS`` and
    ``MAX_EDIT_BYTES``; materializing that edit can legitimately produce a file larger
    than ``MAX_TOTAL_BYTES`` when the repository file was already large before the model
    touched it. In that case, allow exactly the materialized size through the ordinary
    validator so path, file-count, text, Python syntax, and all downstream review and
    promotion gates still run unchanged.
    """
    if not isinstance(proposal, dict):
        return _ORIGINAL_VALIDATE_PROPOSAL(self, proposal, provider_name)

    normalized = self._normalize_proposal_shape(proposal)
    if isinstance(normalized.get("files"), dict) or "edits" not in normalized:
        return _ORIGINAL_VALIDATE_PROPOSAL(self, normalized, provider_name)

    files = self._files_from_edits(normalized.get("edits"))
    materialized = dict(normalized)
    materialized["files"] = files
    materialized.pop("edits", None)

    materialized_total = sum(len(content.encode("utf-8")) for content in files.values())
    had_override = "MAX_TOTAL_BYTES" in self.__dict__
    previous_override = self.__dict__.get("MAX_TOTAL_BYTES")
    self.MAX_TOTAL_BYTES = max(int(self.MAX_TOTAL_BYTES), materialized_total)
    try:
        return _ORIGINAL_VALIDATE_PROPOSAL(self, materialized, provider_name)
    finally:
        if had_override:
            self.__dict__["MAX_TOTAL_BYTES"] = previous_override
        else:
            self.__dict__.pop("MAX_TOTAL_BYTES", None)


def install_compact_edit_materialization_budget() -> None:
    """Install the compact-edit/full-file byte-budget separation exactly once."""
    if getattr(CodingModule, INSTALL_MARKER, False):
        return
    CodingModule.validate_proposal = _validate_proposal_with_compact_edit_materialization_budget
    setattr(CodingModule, INSTALL_MARKER, True)

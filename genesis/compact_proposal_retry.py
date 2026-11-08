"""Explicit bounded retry feedback for malformed or oversized coding proposals.

This changes instructions, never parses/reconstructs invalid code or increases
the edit/file limits. Ordinary validation and independent promotion remain.
"""
from __future__ import annotations

from .coding import CodingModule


INSTALL_MARKER = "_genesis_compact_proposal_retry_installed"
_ORIGINAL_REPAIR_PROMPT = CodingModule._repair_prompt


def _compact_retry_feedback(module: CodingModule, raw: str, error: Exception) -> str:
    message = str(error).lower()
    if "byte limit" in message:
        return (
            "\nCOMPACT_SIZE_RECOVERY: The previous proposal exceeded a strict byte budget. "
            "MAX_EDIT_BYTES is " + str(module.MAX_EDIT_BYTES) + " UTF-8 bytes for replacement edits; "
            "MAX_TOTAL_BYTES is " + str(module.MAX_TOTAL_BYTES) + " bytes for whole-file proposals. "
            "Do NOT emit a files mapping, complete source file, repeated context, or multi-line explanation. "
            "Emit exactly one compact edit in the JSON edits list using an existing path from VALID_PATHS, "
            "the original NUMBERED_CONTEXT line numbers, and a short real replacement under the edit limit. "
            "Use start_line/end_line to replace one complete statement or insert_after_line to add one. "
            "Do not truncate code mechanically, omit required executable bodies, introduce undefined names, "
            "or weaken verification. If the correct fix cannot fit, the provider must not invent a fake fix.\n"
        )
    if any(fragment in message for fragment in (
        "malformed json",
        "did not return a complete json",
        "expecting ',' delimiter",
        "invalid control character",
        "unterminated string",
    )):
        return (
            "\nCOMPACT_JSON_RECOVERY: The previous response was not parseable JSON. "
            "Start with { and end with }; output ONE JSON object, no markdown code fence or prose. "
            'Use only {"edits":[{"path":"<exact VALID_PATHS path>",'
            '"start_line":<integer>,"end_line":<integer>,"new":"<JSON-escaped executable code>"}]}. '
            "Use double quotes around keys and strings, escape embedded newlines as \\n and embedded "
            "quotes as \\", and never use Python triple quotes outside a JSON string. "
            "Choose a short, syntactically complete edit grounded in NUMBERED_CONTEXT; "
            "do not output a files mapping or a partial JSON object.\n"
        )
    return ""


def _repair_prompt_with_compact_feedback(
    self: CodingModule,
    original_prompt: str,
    raw: str,
    error: Exception,
    attempt: int,
    allowed_paths: tuple[str, ...],
    edit_hint: tuple[str, int],
) -> str:
    base = _ORIGINAL_REPAIR_PROMPT(
        self, original_prompt, raw, error, attempt, allowed_paths, edit_hint
    )
    return base + _compact_retry_feedback(self, raw, error)


def install_compact_proposal_retry() -> None:
    if getattr(CodingModule, INSTALL_MARKER, False):
        return
    CodingModule._repair_prompt = _repair_prompt_with_compact_feedback
    setattr(CodingModule, INSTALL_MARKER, True)

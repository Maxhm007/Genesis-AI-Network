from __future__ import annotations

import ast
import json
from pathlib import Path

from .coding import CodingModule


INSTALL_MARKER = "_genesis_python_syntax_retry_installed"
_ORIGINAL_REPAIR_PROMPT = CodingModule._repair_prompt
MAX_STATEMENT_EXCERPT_LINES = 24
MAX_STATEMENT_EXCERPT_BYTES = 4_000


def _attempted_line_edit(module: CodingModule, raw: str) -> tuple[str, int, int] | None:
    """Recover only an explicit bounded line edit already supplied by the provider."""
    try:
        proposal = module._normalize_proposal_shape(module._extract_json(raw))
    except Exception:
        return None
    edits = proposal.get("edits")
    if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
        return None
    edit = edits[0]
    path_value = edit.get("path")
    start_line = edit.get("start_line")
    end_line = edit.get("end_line")
    if not isinstance(path_value, str) or not path_value.endswith(".py"):
        return None
    if not isinstance(start_line, int) or isinstance(start_line, bool):
        return None
    if not isinstance(end_line, int) or isinstance(end_line, bool):
        return None
    if start_line < 1 or end_line < start_line:
        return None
    path = path_value.replace("\\", "/").lstrip("./")
    return path, start_line, end_line


def _smallest_enclosing_statement(source: str, start_line: int, end_line: int) -> tuple[int, int] | None:
    """Return the smallest original AST statement containing the rejected edit range."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    candidates: list[tuple[int, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        first = getattr(node, "lineno", None)
        last = getattr(node, "end_lineno", first)
        if not isinstance(first, int) or not isinstance(last, int):
            continue
        if first <= start_line and end_line <= last:
            candidates.append((last - first, first, last))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    _, first, last = candidates[0]
    return first, last


def _numbered_excerpt(source: str, first: int, last: int) -> str:
    lines = source.splitlines()
    if first < 1 or last < first or first > len(lines):
        return ""
    clipped_last = min(last, len(lines), first + MAX_STATEMENT_EXCERPT_LINES - 1)
    excerpt = "\n".join(f"{line_no}|{lines[line_no - 1]}" for line_no in range(first, clipped_last + 1))
    data = excerpt.encode("utf-8")[:MAX_STATEMENT_EXCERPT_BYTES]
    text = data.decode("utf-8", errors="ignore")
    if clipped_last < last:
        text += f"\n... statement continues through line {last}"
    return text


def _syntax_retry_guidance(module: CodingModule, raw: str, error: Exception) -> str:
    if "invalid Python syntax" not in str(error):
        return ""
    attempted = _attempted_line_edit(module, raw)
    if attempted is None:
        return ""
    path, start_line, end_line = attempted
    target = (module.root / path).resolve()
    try:
        target.relative_to(module.root)
    except ValueError:
        return ""
    if not target.is_file():
        return ""
    source = target.read_text(encoding="utf-8")
    statement_range = _smallest_enclosing_statement(source, start_line, end_line)
    if statement_range is None:
        return (
            f"\nPYTHON_SYNTAX_RECOVERY: rejected edit range {path}:{start_line}-{end_line}. "
            "No single original AST statement contains that full range. Choose a different complete standalone "
            "statement from NUMBERED_CONTEXT; do not retry an interior fragment.\n"
        )
    first, last = statement_range
    excerpt = _numbered_excerpt(source, first, last)
    return (
        "\nPYTHON_SYNTAX_RECOVERY: The previous edit cut through valid Python structure.\n"
        f"REJECTED_EDIT_RANGE: {path}:{start_line}-{end_line}\n"
        f"AST_SAFE_STATEMENT_RANGE: {path}:{first}-{last}\n"
        f"AST_SAFE_STATEMENT_CONTEXT:\n{excerpt}\n"
        "NEXT_RETRY_RULE: Either replace exactly the complete AST_SAFE_STATEMENT_RANGE with one syntactically "
        "complete statement, or choose a different complete standalone statement from NUMBERED_CONTEXT. "
        "Do not edit only an interior line of this statement. Preserve surrounding block structure and indentation.\n"
    )


def _retry_sequence_guidance(module: CodingModule, attempt: int) -> str:
    """Make deterministic syntax retries materially different across bounded attempts."""
    next_attempt = max(2, min(module.MAX_PROPOSAL_ATTEMPTS, int(attempt) + 1))
    guidance = f"\nPYTHON_SYNTAX_RETRY_ATTEMPT: {next_attempt}/{module.MAX_PROPOSAL_ATTEMPTS}\n"
    if next_attempt >= module.MAX_PROPOSAL_ATTEMPTS:
        guidance += (
            "FINAL_PYTHON_SYNTAX_RETRY: The previous AST-guided retry also failed. "
            "Do not repeat the same path/range/replacement combination shown in PREVIOUS. "
            "Use OBJECTIVE plus AST_SAFE_STATEMENT_CONTEXT/NUMBERED_CONTEXT to choose a materially different, "
            "syntactically complete one-edit strategy on the same valid path. If the previous edit used an interior "
            "fragment, use the exact AST-safe statement boundary; if that exact boundary/replacement already failed, "
            "choose a different complete standalone statement relevant to OBJECTIVE. Never weaken validation or tests.\n"
        )
    else:
        guidance += (
            "PYTHON_SYNTAX_RETRY_STRATEGY: Apply the AST-safe boundary guidance and do not repeat the rejected "
            "path/range/replacement combination from PREVIOUS. Return exactly one syntactically complete edit.\n"
        )
    return guidance


def _repair_prompt_with_ast_guidance(
    self: CodingModule,
    original_prompt: str,
    raw: str,
    error: Exception,
    attempt: int,
    allowed_paths: tuple[str, ...],
    edit_hint: tuple[str, int],
) -> str:
    base = _ORIGINAL_REPAIR_PROMPT(self, original_prompt, raw, error, attempt, allowed_paths, edit_hint)
    syntax_guidance = _syntax_retry_guidance(self, raw, error)
    if not syntax_guidance:
        return base
    return base + syntax_guidance + _retry_sequence_guidance(self, attempt)


def install_python_syntax_retry_guidance() -> None:
    """Install deterministic AST guidance for bounded Python syntax retries once."""
    if getattr(CodingModule, INSTALL_MARKER, False):
        return
    CodingModule._repair_prompt = _repair_prompt_with_ast_guidance
    setattr(CodingModule, INSTALL_MARKER, True)

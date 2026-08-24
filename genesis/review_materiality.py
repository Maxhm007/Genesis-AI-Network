from __future__ import annotations

"""Reject autonomous candidates that do not create reachable useful behavior.

Tests and model review can prove compatibility, but they do not prove that a
candidate materially changes capability.  This gate is deterministic and runs
before the existing current-main review/validation path.  It never replaces
Security, tests, independent validators, signing, quorum, or promotion checks.
"""

import ast
import subprocess
from pathlib import Path
from typing import Any

from .autonomy_pipeline import PipelineRecord, ReviewWorker
from .current_main_review import _prepare_candidate_on_current_main, _restore_exact_candidate


INSTALL_MARKER = "_genesis_review_materiality_installed"
_ORIGINAL_RUN_ATTR = "_genesis_review_materiality_original_run"
_TERMINAL_STATEMENTS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def _stmt_dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def _statement_lists(tree: ast.AST):
    for node in ast.walk(tree):
        for _field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
                yield value


def _adjacent_duplicate_count(source: str) -> int:
    tree = ast.parse(source)
    count = 0
    for statements in _statement_lists(tree):
        previous: str | None = None
        for statement in statements:
            current = _stmt_dump(statement)
            if previous == current:
                count += 1
            previous = current
    return count


def _unreachable_statement_count(source: str) -> int:
    tree = ast.parse(source)
    count = 0
    for statements in _statement_lists(tree):
        terminated = False
        for statement in statements:
            if terminated:
                count += 1
                continue
            if isinstance(statement, _TERMINAL_STATEMENTS):
                terminated = True
    return count


class _ReachableRuntimeNormalizer(ast.NodeTransformer):
    """Drop docstrings and statements unreachable after an unconditional exit."""

    def generic_visit(self, node: ast.AST) -> ast.AST:
        node = super().generic_visit(node)
        for field, value in ast.iter_fields(node):
            if not isinstance(value, list) or not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            statements = list(value)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if (
                    statements
                    and isinstance(statements[0], ast.Expr)
                    and isinstance(statements[0].value, ast.Constant)
                    and isinstance(statements[0].value.value, str)
                ):
                    statements = statements[1:]
            reachable: list[ast.stmt] = []
            for statement in statements:
                reachable.append(statement)
                if isinstance(statement, _TERMINAL_STATEMENTS):
                    break
            setattr(node, field, reachable)
        return node


def _reachable_runtime_fingerprint(source: str) -> str:
    tree = ast.parse(source)
    normalized = _ReachableRuntimeNormalizer().visit(tree)
    ast.fix_missing_locations(normalized)
    return ast.dump(normalized, include_attributes=False)


def evaluate_python_materiality(
    base_source: str,
    candidate_source: str,
    *,
    require_behavior_change: bool,
) -> tuple[bool, str]:
    """Return whether a Python candidate is materially acceptable.

    Any autonomous Python patch is rejected if it introduces adjacent duplicate
    statements or new unreachable statements. Capability-growth work has the
    additional requirement that its reachable runtime AST must actually change.
    """
    try:
        base_duplicates = _adjacent_duplicate_count(base_source)
        candidate_duplicates = _adjacent_duplicate_count(candidate_source)
        base_unreachable = _unreachable_statement_count(base_source)
        candidate_unreachable = _unreachable_statement_count(candidate_source)
        base_fingerprint = _reachable_runtime_fingerprint(base_source)
        candidate_fingerprint = _reachable_runtime_fingerprint(candidate_source)
    except SyntaxError as exc:
        return False, f"materiality_gate:python_parse_error:{exc.msg}"

    if candidate_duplicates > base_duplicates:
        return False, "materiality_gate:introduced_adjacent_duplicate_statement"
    if candidate_unreachable > base_unreachable:
        return False, "materiality_gate:introduced_unreachable_statement"
    if require_behavior_change and candidate_fingerprint == base_fingerprint:
        return False, "materiality_gate:no_reachable_behavior_change"
    return True, "materiality_gate:pass"


def _normalize(path: object) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def _git(worker: ReviewWorker, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=worker.root,
        text=True,
        capture_output=True,
        check=False,
    )


def _is_capability_growth(task: Any, record: PipelineRecord) -> bool:
    payload = dict(getattr(task, "payload", {}) or {})
    if str(payload.get("task_type") or "") == "capability_growth":
        return True
    discovery = dict(record.discovery or {})
    return bool(discovery.get("benchmark_gap")) or str(discovery.get("status") or "") == "capability_growth_enqueued"


def _materiality_review_run(worker: ReviewWorker, record: PipelineRecord) -> dict:
    original_run = getattr(ReviewWorker, _ORIGINAL_RUN_ATTR)
    if not record.candidate_sha or not record.candidate_branch or not record.review_ref:
        return original_run(worker, record)

    ok, feedback, _diff, current_main_sha = _prepare_candidate_on_current_main(worker, record)
    if not ok:
        if record.candidate_sha:
            _restore_exact_candidate(worker, str(record.candidate_sha))
        return worker._send_back(record, feedback)

    target = _normalize(record.target_path)
    task = worker.engineering.queue.get(record.task_id)
    gate_ok = True
    gate_feedback = "materiality_gate:pass"
    if target.endswith(".py"):
        base = _git(worker, "show", f"{current_main_sha}:{target}")
        if base.returncode != 0:
            gate_ok = False
            gate_feedback = "materiality_gate:base_source_unavailable"
        else:
            candidate_path = Path(worker.root) / target
            try:
                candidate_source = candidate_path.read_text(encoding="utf-8")
            except OSError:
                gate_ok = False
                gate_feedback = "materiality_gate:candidate_source_unavailable"
            else:
                gate_ok, gate_feedback = evaluate_python_materiality(
                    base.stdout,
                    candidate_source,
                    require_behavior_change=_is_capability_growth(task, record),
                )

    restored, restore_error = _restore_exact_candidate(worker, str(record.candidate_sha))
    if not restored:
        return worker._send_back(record, restore_error)
    if not gate_ok:
        return worker._send_back(record, gate_feedback)

    return original_run(worker, record)


def install_review_materiality_gate() -> None:
    """Install after current-main review so its authoritative gates stay intact."""
    if getattr(ReviewWorker, INSTALL_MARKER, False):
        return
    setattr(ReviewWorker, _ORIGINAL_RUN_ATTR, ReviewWorker.run)
    ReviewWorker.run = _materiality_review_run
    setattr(ReviewWorker, INSTALL_MARKER, True)

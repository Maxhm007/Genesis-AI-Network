from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


TASK_TITLE_PREFIX = "[Genesis Task] self repair"
TARGET_RE = re.compile(r"^- \*\*Target:\*\* `(?P<path>genesis/[A-Za-z0-9_./-]+\.py)`$", re.MULTILINE)
EVIDENCE_RE = re.compile(r"Grounding evidence: (?P<test>test_[A-Za-z0-9_]+)\b")


def _label_names(issue: dict) -> set[str]:
    names: set[str] = set()
    for label in issue.get("labels") or []:
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            names.add(label["name"])
    return names


def _matching_tests(root: Path, test_name: str) -> list[Path]:
    matches: list[Path] = []
    tests_root = (root / "tests").resolve()
    if not tests_root.is_dir():
        return matches
    for path in tests_root.rglob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError):
            continue
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name for node in ast.walk(tree)):
            matches.append(path.resolve())
    return matches


def reconciliation_plan(issue: dict, root: Path) -> dict:
    root = root.resolve()
    labels = _label_names(issue)
    body = str(issue.get("body") or "")
    title = str(issue.get("title") or "")
    state = str(issue.get("state") or "").upper()

    required_labels = {"genesis-autonomous", "genesis-task"}
    if state != "OPEN" or not required_labels.issubset(labels):
        return {"eligible": False, "reason": "issue is not an open autonomous Genesis task"}
    if not title.startswith(TASK_TITLE_PREFIX):
        return {"eligible": False, "reason": "issue is not a machine-generated self-repair task"}
    if "- **Source:** `genesis.issue_discovery`" not in body or "- **Task type:** `self_repair`" not in body:
        return {"eligible": False, "reason": "issue lacks trusted discovery provenance"}

    target_match = TARGET_RE.search(body)
    evidence_match = EVIDENCE_RE.search(body)
    if target_match is None or evidence_match is None:
        return {"eligible": False, "reason": "issue lacks a bounded target or grounding test"}

    target = (root / target_match.group("path")).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return {"eligible": False, "reason": "target escapes repository root"}
    if not target.is_file():
        return {"eligible": False, "reason": "target does not exist on main"}

    test_name = evidence_match.group("test")
    matches = _matching_tests(root, test_name)
    if len(matches) != 1:
        return {"eligible": False, "reason": "grounding test is missing or ambiguous"}

    relative_test = matches[0].relative_to(root).as_posix()
    return {
        "eligible": True,
        "reason": "unique existing grounding test can verify current main",
        "target": target.relative_to(root).as_posix(),
        "test_name": test_name,
        "node_id": f"{relative_test}::{test_name}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan safe reconciliation of an already-satisfied Genesis issue.")
    parser.add_argument("--issue-json", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    issue = json.loads(args.issue_json.read_text(encoding="utf-8"))
    print(json.dumps(reconciliation_plan(issue, args.root), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


LEARNED_CAPABILITY_TARGET = "genesis/learned_capabilities.py"
_REQUIREMENT_PHRASES = (
    "adds one registered executable capability",
    "add one registered executable capability",
    "new registered executable capability",
)


def requires_new_registration(issue_body: str, target: str) -> bool:
    """Return whether this Issue explicitly requires a new learned capability registration."""
    if str(target or "").strip().replace("\\", "/") != LEARNED_CAPABILITY_TARGET:
        return False
    lower = str(issue_body or "").lower()
    return any(phrase in lower for phrase in _REQUIREMENT_PHRASES)


def top_level_registration_names(source: str) -> set[str]:
    """Parse executable top-level register_capability calls and return static names."""
    tree = ast.parse(str(source or ""))
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "register_capability":
            continue
        if len(call.args) < 4:
            continue
        name = call.args[0]
        if isinstance(name, ast.Constant) and isinstance(name.value, str) and name.value.strip():
            names.add(name.value.strip())
    return names


def validate_learned_capability_candidate(
    *,
    issue_body: str,
    target: str,
    base_source: str,
    candidate_source: str,
) -> dict:
    """Independently enforce Issue-level learned-capability structural acceptance."""
    required = requires_new_registration(issue_body, target)
    result = {"required": required, "target": str(target or "")}
    if not required:
        result.update({"ok": True, "added_registrations": []})
        return result

    before = top_level_registration_names(base_source)
    after = top_level_registration_names(candidate_source)
    added = sorted(after - before)
    result["added_registrations"] = added
    result["ok"] = bool(added)
    if not added:
        raise ValueError(
            "semantic acceptance failed: Issue requires a new registered executable "
            "learned capability, but candidate adds no new top-level register_capability call"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-body-file", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--base-file", required=True)
    parser.add_argument("--candidate-file", required=True)
    args = parser.parse_args()
    result = validate_learned_capability_candidate(
        issue_body=Path(args.issue_body_file).read_text(encoding="utf-8"),
        target=args.target,
        base_source=Path(args.base_file).read_text(encoding="utf-8"),
        candidate_source=Path(args.candidate_file).read_text(encoding="utf-8"),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

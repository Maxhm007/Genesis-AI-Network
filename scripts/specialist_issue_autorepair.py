from __future__ import annotations

import re
from pathlib import Path

import scripts.github_issue_autorepair as base

# Push marker: wake specialist controller after baseline-test alignment.

PROTECTED_SYSTEM_SCRIPTS = {
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}

_ORIGINAL_CONTEXT = base.candidate_context_paths
_ORIGINAL_ALLOWED = base.allowed_issue_repair_paths


def _explicit_safe_script_paths(text: str, root: Path) -> list[str]:
    rows: list[str] = []
    for raw in re.findall(r"(?:^|[\s`'\"(])((?:scripts)/[A-Za-z0-9_./-]+\.py)", str(text)):
        normalized = raw.replace("\\", "/").removeprefix("./")
        if ".." in Path(normalized).parts or normalized in PROTECTED_SYSTEM_SCRIPTS:
            continue
        if not (root / normalized).is_file():
            continue
        if normalized not in rows:
            rows.append(normalized)
    return rows


def specialist_context_paths(
    issue_text: str,
    root: Path = base.ROOT,
    limit: int = base.MAX_CONTEXT_FILES,
) -> list[str]:
    """Prefer the explicit safe system-script target for specialist repairs.

    Specialist issues are admitted only after the workflow has independently
    verified a bounded ``scripts/*.py`` target. Ground the coding provider on that
    exact source before any lexical package-code fallback so a follow-up issue
    cannot drift into unrelated ``genesis/*.py`` files.
    """
    bounded = max(1, min(int(limit), base.MAX_CONTEXT_FILES))
    explicit = _explicit_safe_script_paths(issue_text, root)
    if explicit:
        rows: list[str] = []
        for source in explicit:
            rows.append(source)
            test = f"tests/test_{Path(source).stem}.py"
            if (root / test).is_file() and test not in rows:
                rows.append(test)
            if len(rows) >= bounded:
                break
        return rows[:bounded]
    return _ORIGINAL_CONTEXT(issue_text, root, limit)


def specialist_allowed_paths(context_paths: list[str]) -> set[str]:
    allowed = _ORIGINAL_ALLOWED(context_paths)
    for relative in context_paths:
        path = Path(relative)
        if relative.startswith("scripts/") and path.suffix == ".py":
            allowed.add(f"tests/test_{path.stem}.py")
    return allowed


def install() -> None:
    base.candidate_context_paths = specialist_context_paths
    base.allowed_issue_repair_paths = specialist_allowed_paths


def main() -> None:
    install()
    base.main()


if __name__ == "__main__":
    main()

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .github_issue_task_router import issue_authority_enabled
from .github_issue_terminal_reconciler import GithubRequester, _github_request, _issue_labels, _protected_issue


TARGET_RE = re.compile(r"^- \*\*Target:\*\* `(?P<path>genesis/[A-Za-z0-9_./-]+\.py)`$", re.MULTILINE)
OBSERVED_RE = re.compile(r"^- \*\*Observed defect:\*\* (?P<text>.+)$", re.MULTILINE)
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
ACTIVE_LABELS = {"genesis-repair-in-progress", "genesis-validating"}
PROTECTED_TARGETS = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/issue_solver.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
}

TestRunner = Callable[[list[str], Path], bool]
DependencyPreparer = Callable[[Path], bool]


def _looks_like_source_fragment(fragment: str) -> bool:
    text = fragment.strip()
    return any(
        token in text
        for token in (
            " return ",
            "return ",
            " > ",
            " < ",
            " >= ",
            " <= ",
            " == ",
            " != ",
            " = ",
        )
    )


def _observed_bad_fragment(body: str) -> str:
    match = OBSERVED_RE.search(body)
    if match is None:
        return ""
    candidates = [
        fragment.strip()
        for fragment in BACKTICK_RE.findall(match.group("text"))
        if _looks_like_source_fragment(fragment)
    ]
    return max(candidates, key=len) if candidates else ""


def _safe_target(root: Path, body: str) -> tuple[str, Path] | None:
    match = TARGET_RE.search(body)
    if match is None:
        return None
    relative = match.group("path").strip()
    if relative in PROTECTED_TARGETS or ".." in relative:
        return None
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return relative, target


def _focused_test(root: Path, target: Path) -> Path | None:
    candidate = (root / "tests" / f"test_{target.stem}.py").resolve()
    tests_root = (root / "tests").resolve()
    try:
        candidate.relative_to(tests_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _default_prepare_dependencies(root: Path) -> bool:
    try:
        import pytest  # noqa: F401
        import cryptography  # noqa: F401
        return True
    except ImportError:
        requirements = root / "requirements.txt"
        if not requirements.is_file():
            return False
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0


def _default_test_runner(args: list[str], root: Path) -> bool:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=360,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _open_issues(requester: GithubRequester) -> list[dict] | None:
    issues: list[dict] = []
    for page in range(1, 21):
        fetched = requester(
            "GET",
            f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}",
            None,
        )
        if not isinstance(fetched, list):
            return None
        rows = [row for row in fetched if isinstance(row, dict) and not row.get("pull_request")]
        issues.extend(rows)
        if len(fetched) < 100:
            break
    return issues


def reconcile_satisfied_detected_issues(
    root: Path,
    *,
    requester: GithubRequester | None = None,
    runner: TestRunner | None = None,
    prepare_dependencies: DependencyPreparer | None = None,
) -> dict:
    """Verify and close one already-satisfied machine-detected regression.

    This is intentionally narrower than repair. It only trusts bot-authored
    ``[Genesis Detected]`` Issues with a safe explicit Python target and an exact
    backticked bad source fragment in ``Observed defect``. The shortcut closes
    nothing unless that bad fragment is absent from current main, the target
    compiles, a matching focused test exists and passes, and the full repository
    test suite passes. Any uncertainty falls back to the normal repair queue.
    """
    root = Path(root).resolve()
    explicit_requester = requester is not None
    enforced = bool(explicit_requester or issue_authority_enabled(root))
    result = {
        "status": "ok",
        "enforced": enforced,
        "scanned": 0,
        "candidate": None,
        "closed": [],
        "skipped": [],
        "blocked": [],
    }
    if not enforced:
        result["status"] = "not_repository_runtime"
        return result

    requester = requester or _github_request
    runner = runner or _default_test_runner
    prepare_dependencies = prepare_dependencies or _default_prepare_dependencies
    issues = _open_issues(requester)
    if issues is None:
        result["blocked"].append({"reason": "github_open_issues_unavailable"})
        return result
    result["scanned"] = len(issues)

    candidate: dict | None = None
    for issue in issues:
        number = int(issue.get("number") or 0)
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        author = str((issue.get("user") or {}).get("login") or "")
        labels = _issue_labels(issue)

        if str(issue.get("state") or "open").lower() != "open":
            continue
        if author != "github-actions[bot]" or not title.startswith("[Genesis Detected]"):
            continue
        if _protected_issue(issue) or labels & ACTIVE_LABELS:
            result["skipped"].append({"github_issue_number": number, "reason": "protected_or_active"})
            continue

        target_info = _safe_target(root, body)
        bad_fragment = _observed_bad_fragment(body)
        if target_info is None or not bad_fragment:
            result["skipped"].append({"github_issue_number": number, "reason": "missing_exact_safe_evidence"})
            continue
        relative_target, target = target_info
        focused = _focused_test(root, target)
        if focused is None:
            result["skipped"].append({"github_issue_number": number, "reason": "focused_test_missing"})
            continue

        try:
            source = target.read_text(encoding="utf-8")
            compile(source, relative_target, "exec")
        except (OSError, UnicodeError, SyntaxError) as exc:
            result["skipped"].append(
                {"github_issue_number": number, "reason": f"target_not_compilable:{type(exc).__name__}"}
            )
            continue
        if bad_fragment in source:
            result["skipped"].append({"github_issue_number": number, "reason": "reported_bad_fragment_still_present"})
            continue

        candidate = {
            "github_issue_number": number,
            "target": relative_target,
            "focused_test": focused.relative_to(root).as_posix(),
            "bad_fragment": bad_fragment,
        }
        break

    result["candidate"] = candidate
    if candidate is None:
        return result

    number = int(candidate["github_issue_number"])
    claimed = requester("POST", f"/issues/{number}/labels", {"labels": ["genesis-validating"]})
    if not isinstance(claimed, (list, dict)):
        result["blocked"].append({"github_issue_number": number, "reason": "validation_claim_failed"})
        return result

    def release_validation_claim() -> None:
        requester("DELETE", f"/issues/{number}/labels/genesis-validating", None)

    if not prepare_dependencies(root):
        release_validation_claim()
        result["blocked"].append({"github_issue_number": number, "reason": "test_dependencies_unavailable"})
        return result

    focused_args = ["-q", str(candidate["focused_test"])]
    if not runner(focused_args, root):
        release_validation_claim()
        result["blocked"].append({"github_issue_number": number, "reason": "focused_test_failed"})
        return result
    if not runner(["-q"], root):
        release_validation_claim()
        result["blocked"].append({"github_issue_number": number, "reason": "full_test_suite_failed"})
        return result

    evidence = (
        "Genesis terminal verification found this machine-detected regression already satisfied on current `main`.\n\n"
        f"- Target: `{candidate['target']}` compiled successfully.\n"
        f"- Reported bad fragment is absent: `{candidate['bad_fragment']}`.\n"
        f"- Focused verification passed: `python -m pytest -q {candidate['focused_test']}`.\n"
        "- Full repository verification passed: `python -m pytest -q`.\n"
        "- No repair candidate or code promotion was needed.\n\n"
        "Genesis is closing the Issue as completed because its reported defect is no longer present and all required verification passed."
    )
    comment = requester("POST", f"/issues/{number}/comments", {"body": evidence})
    verified = requester("POST", f"/issues/{number}/labels", {"labels": ["genesis-verified"]})
    if not isinstance(comment, dict) or not isinstance(verified, (list, dict)):
        release_validation_claim()
        result["blocked"].append({"github_issue_number": number, "reason": "verification_evidence_publish_failed"})
        return result

    updated = requester("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
    release_validation_claim()
    if isinstance(updated, dict) and str(updated.get("state") or "") == "closed":
        result["closed"].append(number)
    else:
        result["blocked"].append({"github_issue_number": number, "reason": "github_close_failed"})
    return result

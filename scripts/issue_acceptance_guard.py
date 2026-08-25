from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STOPWORDS = {
    "about", "after", "before", "could", "does", "from", "have", "into",
    "issue", "should", "that", "their", "there", "these", "this", "when",
    "where", "which", "with", "fix", "bug", "change", "required", "system",
}
REQUEST_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(?:required(?:\s+system)?\s+(?:improvement|fix|change)|requirements?|acceptance(?:\s+criteria)?|expected(?:\s+behavior)?|requested\s+change|remediation|fix)\s*:?\s*$"
)
PRODUCTION_PREFIXES = ("genesis/", "scripts/")
TEST_PREFIX = "tests/test_"
CANDIDATE_TEST_PROVIDER_ENV = (
    "GENESIS_PROVIDER_URL",
    "GENESIS_PROVIDER_NAME",
    "GENESIS_PROVIDER_TIMEOUT_SECONDS",
    "GENESIS_PROVIDER_MAX_NEW_TOKENS",
    "GENESIS_PROVIDER_ENDPOINTS",
)


def _run(args: list[str], *, root: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, text=True, capture_output=True, check=False, env=env)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], root=root)


def _tokens(text: str) -> set[str]:
    values = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", str(text))
    }
    return {token for token in values if token not in STOPWORDS}


def request_focus(issue_text: str) -> str:
    text = str(issue_text)
    title = ""
    for line in text.splitlines()[:4]:
        if line.startswith("TITLE:"):
            title = line
            break
    match = REQUEST_HEADING_RE.search(text)
    if match is None:
        return text
    tail = text[match.start() :]
    return (title + "\n" + tail).strip() if title else tail


def _show(root: Path, ref: str, path: str) -> str | None:
    result = _git(root, "show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else None


def _ast_dump(text: str | None) -> str | None:
    if text is None:
        return None
    try:
        return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)
    except SyntaxError:
        return None


def changed_paths(root: Path, base_ref: str) -> list[str]:
    result = _git(root, "diff", "--name-only", f"{base_ref}...HEAD")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "git diff failed")[-1200:])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _candidate_test_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in CANDIDATE_TEST_PROVIDER_ENV:
        env.pop(name, None)
    env["PYTHONPATH"] = str(root)
    return env


def _run_candidate_tests(root: Path, tests: list[str]) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-m", "pytest", "-q", *tests], root=root, env=_candidate_test_env(root))


def _run_candidate_tests_on_base(root: Path, base_ref: str, tests: list[str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="genesis-issue-acceptance-") as tmp:
        worktree = Path(tmp) / "base"
        add = _git(root, "worktree", "add", "--detach", str(worktree), base_ref)
        if add.returncode != 0:
            raise RuntimeError((add.stderr or add.stdout or "git worktree add failed")[-1200:])
        try:
            for relative in tests:
                candidate = root / relative
                if not candidate.is_file():
                    raise RuntimeError(f"candidate regression test is missing: {relative}")
                target = worktree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(candidate, target)
            return _run_candidate_tests(worktree, tests)
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))


def evaluate_candidate(root: Path, base_ref: str, issue_text: str) -> dict:
    root = Path(root).resolve()
    changed = changed_paths(root, base_ref)
    production = [
        path for path in changed
        if path.endswith(".py") and path.startswith(PRODUCTION_PREFIXES) and not path.startswith("tests/")
    ]
    tests = [path for path in changed if path.startswith(TEST_PREFIX) and path.endswith(".py")]

    result = {
        "status": "rejected",
        "base_ref": base_ref,
        "changed_files": changed,
        "production_files": production,
        "regression_tests": tests,
    }
    if not production:
        result["reason"] = "no_production_python_change"
        return result
    if not tests:
        result["reason"] = "no_changed_regression_test"
        return result

    semantic_files: list[str] = []
    for relative in production:
        base_text = _show(root, base_ref, relative)
        candidate_path = root / relative
        candidate_text = candidate_path.read_text(encoding="utf-8", errors="replace") if candidate_path.is_file() else None
        base_ast = _ast_dump(base_text)
        candidate_ast = _ast_dump(candidate_text)
        if candidate_ast is None:
            result["reason"] = f"candidate_python_not_parseable:{relative}"
            return result
        if base_ast != candidate_ast:
            semantic_files.append(relative)
    if not semantic_files:
        result["reason"] = "python_ast_unchanged_formatting_or_comment_only"
        return result

    focus = request_focus(issue_text)
    diff = _git(root, "diff", "--unified=0", f"{base_ref}...HEAD", "--", *production, *tests)
    material = "\n".join([*production, *tests, diff.stdout[-12000:]])
    overlap = sorted(_tokens(focus) & _tokens(material))
    if not overlap:
        result["reason"] = "candidate_not_grounded_in_issue_terms"
        return result

    candidate_tests = _run_candidate_tests(root, tests)
    result["candidate_test_returncode"] = candidate_tests.returncode
    result["candidate_test_output"] = (candidate_tests.stdout + "\n" + candidate_tests.stderr)[-2000:]
    if candidate_tests.returncode != 0:
        result["reason"] = "candidate_regression_tests_do_not_pass"
        return result

    base_tests = _run_candidate_tests_on_base(root, base_ref, tests)
    result["base_test_returncode"] = base_tests.returncode
    result["base_test_output"] = (base_tests.stdout + "\n" + base_tests.stderr)[-2000:]
    if base_tests.returncode == 0:
        result["reason"] = "regression_test_also_passes_on_base"
        return result
    if base_tests.returncode != 1:
        result["reason"] = "base_regression_evidence_is_not_a_normal_test_failure"
        return result

    result.update(
        {
            "status": "accepted",
            "reason": "candidate_changes_runtime_semantics_and_regression_test_fails_on_base",
            "semantic_files": semantic_files,
            "issue_term_overlap": overlap[:20],
        }
    )
    return result


def _issue_text(repository: str, issue_number: int) -> str:
    command = [
        "gh", "issue", "view", str(issue_number), "--repo", repository,
        "--json", "title,body",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue lookup failed")[-1200:])
    value = json.loads(result.stdout or "{}")
    if not isinstance(value, dict):
        raise RuntimeError("issue lookup did not return an object")
    title = str(value.get("title") or "").strip()
    body = str(value.get("body") or "").strip()
    return f"TITLE: {title}\nBODY:\n{body}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Require issue-specific semantic regression evidence before autonomous promotion")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-number", required=True, type=int)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    try:
        evidence = evaluate_candidate(ROOT, args.base_ref, _issue_text(args.repository, args.issue_number))
    except Exception as exc:
        evidence = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:1800]}
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence.get("status") == "accepted" else 2)


if __name__ == "__main__":
    main()

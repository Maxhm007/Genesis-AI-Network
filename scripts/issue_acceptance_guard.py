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
MANIFEST_PATH = ".github/workflows/gate/manifest.json"
# Files that decide how tests run or what they see. A fix may never touch them.
TEST_CONFIG_NAMES = {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", ".coveragerc", "noxfile.py"}
# Architecture-plan steps only add a brand-new extension module. They may pass the gate,
# but they are new features, never counted as bug fixes.
ARCHITECTURE_PLAN_MARKER = "<!-- genesis-architecture-plan:"
EXTENSION_PREFIX = "genesis/architecture_extensions/"
# Only people with write access can put text into someone else's issue, so the plan marker is
# trusted only on issues opened by the repository's own people or by Genesis's workflow bot.
TRUSTED_PLAN_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
TRUSTED_PLAN_BOTS = {"github-actions[bot]"}
# Python runs these automatically at startup, so a fix could use one to patch the code under test.
STARTUP_HOOK_NAMES = {"sitecustomize.py", "usercustomize.py"}
# Bot-written tests see only these variables: no tokens, no provider settings, nothing else from the job.
CANDIDATE_TEST_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
# On the old code these only show that a name is missing, not that the bug reproduces.
MISSING_NAME_ERRORS = ("NameError", "ImportError", "ModuleNotFoundError", "AttributeError")
SIGNATURE_ERROR_RE = re.compile(
    r"^TypeError:.*(unexpected keyword argument|positional argument|required (?:keyword-only |positional )?argument)"
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
    env = {name: os.environ[name] for name in CANDIDATE_TEST_ENV_ALLOWLIST if name in os.environ}
    env["PYTHONPATH"] = str(root)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _node_outcomes(report: Path, node_ids: list[str]) -> dict[str, list[tuple[str, str]]]:
    """(outcome, message) for every junit testcase that belongs to each requested node id."""
    import xml.etree.ElementTree as ET

    outcomes: dict[str, list[tuple[str, str]]] = {node: [] for node in node_ids}
    if not report.is_file():
        return outcomes
    wanted: dict[tuple[str, str], str] = {}
    for node in node_ids:
        path, *parts = node.split("::")
        classname = ".".join([path[:-3].replace("/", "."), *parts[:-1]])
        wanted[(classname, parts[-1])] = node
    for case in ET.parse(report).iter("testcase"):
        key = (case.get("classname", ""), case.get("name", "").split("[", 1)[0])
        node = wanted.get(key)
        if node is None:
            continue
        outcome, message = "passed", ""
        for kind in ("failure", "error", "skipped"):
            child = case.find(kind)
            if child is not None:
                outcome, message = kind, (child.get("message") or child.text or "").strip()
                break
        outcomes[node].append((outcome, message))
    return outcomes


def _run_candidate_tests(
    root: Path, tests: list[str], report: Path | None = None
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if report is not None:
        args.append(f"--junitxml={report}")
    return _run([*args, *tests], root=root, env=_candidate_test_env(root))


def _run_candidate_tests_on_base(
    root: Path, base_ref: str, tests: list[str], node_ids: list[str] | None = None, report: Path | None = None
) -> subprocess.CompletedProcess[str]:
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
            return _run_candidate_tests(worktree, node_ids or tests, report)
        finally:
            _git(root, "worktree", "remove", "--force", str(worktree))


def _locked_paths(root: Path, base_ref: str) -> set[str]:
    text = _show(root, base_ref, MANIFEST_PATH)
    if text is None:
        return set()
    try:
        files = json.loads(text).get("files") or {}
    except (ValueError, AttributeError):
        return set()
    return {str(path) for path in files}


def _forbidden_change(path: str, locked: set[str]) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if path in locked or path == MANIFEST_PATH:
        return f"changes_locked_file:{path}"
    if name in TEST_CONFIG_NAMES:
        return f"changes_test_configuration:{path}"
    if name in STARTUP_HOOK_NAMES or name.endswith(".pth"):
        return f"changes_python_startup_hook:{path}"
    if path.startswith("tests/") and not (path.startswith(TEST_PREFIX) and path.endswith(".py")):
        return f"changes_test_support_file:{path}"
    return None


def _test_nodes(tree: ast.Module) -> dict[str, ast.AST]:
    """pytest node suffix (`name` or `Class::name`) for every test function in a module."""
    nodes: dict[str, ast.AST] = {}
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
            nodes[item.name] = item
        elif isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            for member in item.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test"):
                    nodes[f"{item.name}::{member.name}"] = member
    return nodes


def _added_statements(base_items: list[ast.stmt], candidate_items: list[ast.stmt]) -> list[ast.stmt] | None:
    """Candidate statements not matched to the base, or None if a base statement was edited or removed."""
    added: list[ast.stmt] = []
    position = 0
    for item in candidate_items:
        if position < len(base_items) and ast.dump(item) == ast.dump(base_items[position]):
            position += 1
        else:
            added.append(item)
    return added if position == len(base_items) else None


def _is_pytest_mark(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    while isinstance(target, ast.Attribute):
        if isinstance(target.value, ast.Attribute) and target.value.attr == "mark":
            return isinstance(target.value.value, ast.Name) and target.value.value.id == "pytest"
        target = target.value
    return False


def _plain_test_function(item: ast.stmt) -> bool:
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or not item.name.startswith("test"):
        return False
    args = item.args
    if args.defaults or any(default is not None for default in args.kw_defaults):
        return False
    return all(_is_pytest_mark(decorator) for decorator in item.decorator_list)


def _is_docstring(item: ast.stmt) -> bool:
    return isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)


def _bound_names(item: ast.stmt) -> list[str]:
    """Module-level names a statement binds (def, class, import, assignment targets)."""
    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [item.name]
    if isinstance(item, (ast.Import, ast.ImportFrom)):
        return [(alias.asname or alias.name).split(".")[0] for alias in item.names]
    names: list[str] = []
    targets = item.targets if isinstance(item, ast.Assign) else [getattr(item, "target", None)]
    for target in targets:
        if target is not None:
            names.extend(sub.id for sub in ast.walk(target) if isinstance(sub, ast.Name))
    return names


def _import_binding(item: ast.Import | ast.ImportFrom, alias: ast.alias) -> tuple:
    module = item.module if isinstance(item, ast.ImportFrom) else None
    level = item.level if isinstance(item, ast.ImportFrom) else 0
    return (module, level, alias.name, alias.asname)


def _shadowing_problem(base_items: list[ast.stmt], added: list[ast.stmt]) -> str | None:
    """A new statement must not rebind a name the file already has, or one another new statement binds.

    pytest only sees the last definition of a name, so a same-name test silently replaces the old one,
    and a rebound import or helper changes what the existing tests call.
    """
    existing = {name for item in base_items for name in _bound_names(item)}
    # Re-importing exactly what the file already imports changes nothing, so it is allowed.
    same_imports = {_import_binding(item, alias) for item in base_items if isinstance(item, (ast.Import, ast.ImportFrom)) for alias in item.names}
    seen: set[str] = set()
    for item in added:
        if isinstance(item, (ast.Import, ast.ImportFrom)) and all(
            _import_binding(item, alias) in same_imports for alias in item.names
        ):
            continue
        for name in _bound_names(item):
            if name in existing or name in seen:
                return f"new_test_reuses_existing_name:{name}"
            seen.add(name)
        if isinstance(item, ast.ClassDef):
            members = [member.name for member in item.body if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(members) != len(set(members)):
                return f"new_test_class_repeats_a_method_name:{item.name}"
    return None


def _allowed_new_test_statement(item: ast.stmt) -> bool:
    """New code in a test file may only be imports and plain test functions or test classes."""
    if isinstance(item, (ast.Import, ast.ImportFrom)) or _is_docstring(item) or _plain_test_function(item):
        return True
    if isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
        if item.bases or item.keywords or item.decorator_list:
            return False
        return all(_is_docstring(member) or _plain_test_function(member) for member in item.body)
    return False


def _changed_symbols(base_text: str | None, candidate_text: str) -> tuple[set[str], set[str], set[str]]:
    """Symbols whose code differs from the base: (all changed, changed that already existed, callable ones)."""

    callables: set[str] = set()

    def symbols(text: str | None) -> dict[str, str]:
        if text is None:
            return {}
        found: dict[str, str] = {}
        for item in ast.parse(text).body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[item.name] = ast.dump(item)
                callables.add(item.name)
            elif isinstance(item, ast.ClassDef):
                found[item.name] = ast.dump(item)
                callables.add(item.name)
                for member in item.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        found[member.name] = found.get(member.name, "") + ast.dump(member)
                        callables.add(member.name)
            elif isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                for target in targets:
                    for node in ast.walk(target):
                        if isinstance(node, ast.Name):
                            found[node.id] = found.get(node.id, "") + ast.dump(item)
        return found

    before, after = symbols(base_text), symbols(candidate_text)
    changed = {name for name, dump in after.items() if before.get(name) != dump}
    return changed, {name for name in changed if name in before}, callables & changed


def _references(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
    return names


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                names.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                names.add(sub.func.attr)
    return names


def _exercises_existing_change(node: ast.AST, existing: set[str], callables: set[str]) -> bool:
    """The test calls a changed function or class that already existed, or reads a changed existing value."""
    called = _called_names(node) & existing & callables
    read = (_references(node) & existing) - callables
    return bool(called or read)


def _base_failure_problem(outcomes: list[tuple[str, str]], *, new_extension: bool = False) -> str | None:
    if not outcomes:
        return "did_not_run_on_base"
    for outcome, message in outcomes:
        if outcome != "failure":
            return f"{outcome}_on_base"
        kind = message.split(":", 1)[0].strip()
        if new_extension:
            continue  # the module does not exist on the old code, so a missing name is the expected evidence
        if kind in MISSING_NAME_ERRORS:
            return f"fails_on_base_only_because_a_name_is_missing:{kind}"
        if SIGNATURE_ERROR_RE.match(message):
            return "fails_on_base_only_because_the_call_signature_changed"
    return None


def _has_real_assertion(node: ast.AST) -> bool:
    """The test asserts something that is not a literal, or expects an exception."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            try:
                ast.literal_eval(sub.test)
            except ValueError:
                return True
        elif isinstance(sub, ast.With):
            for item in sub.items:
                call = item.context_expr
                func = call.func if isinstance(call, ast.Call) else None
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "raises"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "pytest"
                ):
                    return True
    return False


def evaluate_candidate(root: Path, base_ref: str, issue_text: str, *, trusted_plan: bool = False) -> dict:
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

    locked = _locked_paths(root, base_ref)
    for path in changed:
        problem = _forbidden_change(path, locked)
        if problem:
            result["reason"] = problem
            return result

    # Existing tests stay exactly as they were; the fix may only add new ones.
    new_nodes: dict[str, ast.AST] = {}
    for relative in tests:
        candidate_path = root / relative
        if not candidate_path.is_file():
            result["reason"] = f"deletes_test_file:{relative}"
            return result
        try:
            candidate_tree = ast.parse(candidate_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            result["reason"] = f"candidate_python_not_parseable:{relative}"
            return result
        base_text = _show(root, base_ref, relative)
        base_tree = ast.parse(base_text) if base_text is not None else ast.Module(body=[], type_ignores=[])
        added = _added_statements(base_tree.body, candidate_tree.body)
        if added is None:
            result["reason"] = f"edits_or_removes_existing_test_code:{relative}"
            return result
        for item in added:
            if not _allowed_new_test_statement(item):
                result["reason"] = f"adds_non_test_code_to_test_file:{relative}:{getattr(item, 'lineno', 0)}"
                return result
        shadowing = _shadowing_problem(base_tree.body, added)
        if shadowing:
            result["reason"] = f"{shadowing}:{relative}"
            return result
        base_nodes = _test_nodes(base_tree)
        for name, node in _test_nodes(candidate_tree).items():
            if name not in base_nodes:
                new_nodes[f"{relative}::{name}"] = node
    if not new_nodes:
        result["reason"] = "no_new_regression_test"
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

    # Every new test must exercise the code this fix changed and check a real result.
    changed_symbols: set[str] = set()
    existing_changed: set[str] = set()
    callable_changed: set[str] = set()
    for relative in semantic_files:
        changed, existing, callables = _changed_symbols(
            _show(root, base_ref, relative), (root / relative).read_text(encoding="utf-8")
        )
        changed_symbols |= changed
        existing_changed |= existing
        callable_changed |= callables
    result["changed_symbols"] = sorted(changed_symbols)[:40]
    result["existing_changed_symbols"] = sorted(existing_changed)[:40]
    new_extension = trusted_plan and ARCHITECTURE_PLAN_MARKER in issue_text and all(
        path.startswith(EXTENSION_PREFIX) and _show(root, base_ref, path) is None for path in production
    )
    result["change_kind"] = "new_extension" if new_extension else "bug_fix"
    if not existing_changed and not new_extension:
        result["reason"] = "fix_only_adds_new_code_and_changes_nothing_that_existed"
        return result
    for node_id, node in sorted(new_nodes.items()):
        if not (_references(node) & changed_symbols):
            result["reason"] = f"new_test_does_not_call_changed_code:{node_id}"
            return result
        if not new_extension and not _exercises_existing_change(node, existing_changed, callable_changed):
            result["reason"] = f"new_test_does_not_call_changed_existing_code:{node_id}"
            return result
        if not new_extension and any(isinstance(sub, (ast.Try, getattr(ast, "TryStar", ast.Try))) for sub in ast.walk(node)):
            # A try/except can turn "the name does not exist yet" into an AssertionError.
            result["reason"] = f"new_test_uses_try_except:{node_id}"
            return result
        if not _has_real_assertion(node):
            result["reason"] = f"new_test_has_no_real_assertion:{node_id}"
            return result
    node_ids = sorted(new_nodes)
    result["new_regression_tests"] = node_ids

    focus = request_focus(issue_text)
    diff = _git(root, "diff", "--unified=0", f"{base_ref}...HEAD", "--", *production, *tests)
    material = "\n".join([*production, *tests, diff.stdout[-12000:]])
    overlap = sorted(_tokens(focus) & _tokens(material))
    if not overlap:
        result["reason"] = "candidate_not_grounded_in_issue_terms"
        return result

    candidate_tests = _run_candidate_tests(root, node_ids)
    result["candidate_test_returncode"] = candidate_tests.returncode
    result["candidate_test_output"] = (candidate_tests.stdout + "\n" + candidate_tests.stderr)[-2000:]
    if candidate_tests.returncode != 0:
        result["reason"] = "candidate_regression_tests_do_not_pass"
        return result

    with tempfile.TemporaryDirectory(prefix="genesis-issue-acceptance-report-") as report_dir:
        report = Path(report_dir) / "base.xml"
        base_tests = _run_candidate_tests_on_base(root, base_ref, tests, node_ids, report)
        outcomes = _node_outcomes(report, node_ids)
    result["base_test_returncode"] = base_tests.returncode
    result["base_test_output"] = (base_tests.stdout + "\n" + base_tests.stderr)[-2000:]
    if base_tests.returncode == 0:
        result["reason"] = "regression_test_also_passes_on_base"
        return result
    if base_tests.returncode != 1:
        result["reason"] = "base_regression_evidence_is_not_a_normal_test_failure"
        return result
    for node_id in node_ids:
        problem = _base_failure_problem(outcomes[node_id], new_extension=new_extension)
        if problem:
            result["reason"] = f"base_failure_is_not_the_bug:{node_id}:{problem}"
            return result

    result.update(
        {
            "status": "accepted",
            "reason": (
                "new_architecture_extension_with_regression_test"
                if new_extension
                else "candidate_changes_runtime_semantics_and_regression_test_fails_on_base"
            ),
            "semantic_files": semantic_files,
            "issue_term_overlap": overlap[:20],
        }
    )
    return result


def _trusted_plan_author(issue: dict) -> bool:
    login = str((issue.get("user") or {}).get("login") or "")
    return str(issue.get("author_association") or "") in TRUSTED_PLAN_ASSOCIATIONS or login in TRUSTED_PLAN_BOTS


def _issue(repository: str, issue_number: int) -> tuple[str, bool]:
    """Issue text for the guard, and whether its author may carry an architecture plan."""
    command = ["gh", "api", f"repos/{repository}/issues/{int(issue_number)}"]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "issue lookup failed")[-1200:])
    value = json.loads(result.stdout or "{}")
    if not isinstance(value, dict):
        raise RuntimeError("issue lookup did not return an object")
    title = str(value.get("title") or "").strip()
    body = str(value.get("body") or "").strip()
    return f"TITLE: {title}\nBODY:\n{body}", _trusted_plan_author(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Require issue-specific semantic regression evidence before autonomous promotion")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-number", required=True, type=int)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    try:
        issue_text, trusted_plan = _issue(args.repository, args.issue_number)
        evidence = evaluate_candidate(ROOT, args.base_ref, issue_text, trusted_plan=trusted_plan)
    except Exception as exc:
        evidence = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:1800]}
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence.get("status") == "accepted" else 2)


if __name__ == "__main__":
    main()

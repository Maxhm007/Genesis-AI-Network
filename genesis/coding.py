from __future__ import annotations

import ast
import collections
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

from .intelligence_router import IntelligenceRouter
from .memory import GenesisMemory
from .architecture_decomposer import validate_architecture_source
from .providers import IntelligenceProvider, ProviderRegistry
from .self_learning import SelfLearningStore
from .selfdev import SelfDevelopmentExecutor, SelfDevResult


_REVIEW_PACKAGE_DIR = Path(__file__).resolve().parent
# Runs in a fresh `python -I` process that loads only the locked reviewer and
# redaction files under a private package name. Nothing Genesis imports or
# patches at runtime (genesis/__init__.py hooks, monkeypatches, sys.modules
# tricks) exists in that process, so it cannot switch the review off.
_ISOLATED_REVIEW_SCRIPT = """
import json, sys, types
from pathlib import Path
base = Path(sys.argv[1])
package = types.ModuleType("_genesis_isolated_review")
package.__path__ = []  # no directory lookup: a same-named folder or .so cannot be picked up
sys.modules[package.__name__] = package
def load(name):
    # Execute the exact locked source file; never the import system or a cached .pyc.
    module = types.ModuleType(package.__name__ + "." + name)
    module.__package__ = package.__name__
    module.__file__ = str(base / (name + ".py"))
    sys.modules[module.__name__] = module
    source = (base / (name + ".py")).read_text(encoding="utf-8")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module
load("log_redaction")
review = load("change_review")
data = json.load(sys.stdin)
try:
    review.enforce_review(data["current"], data["proposed"])
except ValueError as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
else:
    print(json.dumps({"ok": True}))
"""


def run_isolated_review(current: dict[str, str], proposed: dict[str, str]) -> None:
    """Fail closed unless the isolated reviewer explicitly approves the change."""
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _ISOLATED_REVIEW_SCRIPT, str(_REVIEW_PACKAGE_DIR)],
            input=json.dumps({"current": current, "proposed": proposed}),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        verdict = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.stdout.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError(f"independent change review could not run: {type(exc).__name__}") from exc
    if completed.returncode != 0 or not isinstance(verdict, dict):
        raise ValueError("independent change review could not run")
    if verdict.get("ok") is True:
        return
    raise ValueError(str(verdict.get("error") or "independent change review rejected this proposal"))


def _code_shape(source: str) -> str:
    """AST dump without comments, docstrings, bare values, pass, ... and dead `if False:` blocks."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if not isinstance(body, list):
                continue
            kept = [
                statement
                for statement in body
                if not isinstance(statement, ast.Pass)
                and not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, (ast.Constant, ast.Name, ast.JoinedStr))
                )
                and not (
                    isinstance(statement, ast.If)
                    and isinstance(statement.test, ast.Constant)
                    and not statement.test.value
                    and not statement.orelse
                )
            ]
            setattr(node, field, kept)
    return ast.dump(tree, include_attributes=False)


def _changes_code(old: str, new: str) -> bool:
    try:
        empty = _code_shape("")
        new_shape = _code_shape(new)
        if not old:
            return new_shape != empty
        return _code_shape(old) != new_shape
    except SyntaxError:
        return True


_IMPLICIT_NAMES = frozenset(
    {
        "__file__", "__name__", "__doc__", "__spec__", "__path__", "__builtins__", "__cached__",
        "__loader__", "__package__", "__annotations__", "__dict__", "__class__", "__module__", "__qualname__",
    }
)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def _is_dead_test(test: ast.AST) -> bool:
    return isinstance(test, ast.Constant) and not test.value


class _Scope:
    def __init__(self, kind: str, qual: str, parent: "_Scope | None") -> None:
        self.kind = kind
        self.qual = qual
        self.parent = parent
        self.stores: set[str] = set()
        self.declared_global: set[str] = set()
        self.declared_nonlocal: set[str] = set()
        self.loads: set[str] = set()


def _collect_scopes(tree: ast.Module) -> tuple[list[_Scope], bool]:
    module = _Scope("module", "<module>", None)
    scopes = [module]
    star = False

    def child(kind: str, name: str, parent: _Scope) -> _Scope:
        scope = _Scope(kind, name if parent is module else f"{parent.qual}.{name}", parent)
        scopes.append(scope)
        return scope

    def bind(scope: _Scope, name: str, dead: bool) -> None:
        if not dead:
            scope.stores.add(name)

    def bind_params(scope: _Scope, node: ast.AST) -> None:
        for param in getattr(node, "type_params", None) or []:
            scope.stores.add(param.name)

    def walk_args(args: ast.arguments, outer: _Scope, inner: _Scope, typed: _Scope | None = None) -> None:
        for default in [*args.defaults, *[d for d in args.kw_defaults if d is not None]]:
            visit(default, outer, False)
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if arg is not None:
                inner.stores.add(arg.arg)
                if arg.annotation is not None:
                    visit(arg.annotation, typed or outer, False)

    def visit(node: ast.AST, scope: _Scope, dead: bool) -> None:
        nonlocal star
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for item in node.decorator_list:
                visit(item, scope, dead)
            bind(scope, node.name, dead)
            inner = child("function", node.name, scope)
            bind_params(inner, node)
            typed = inner if getattr(node, "type_params", None) else scope
            if node.returns is not None:
                visit(node.returns, typed, dead)
            walk_args(node.args, scope, inner, typed)
            for statement in node.body:
                visit(statement, inner, False)
        elif isinstance(node, ast.Lambda):
            inner = child("function", "<lambda>", scope)
            walk_args(node.args, scope, inner)
            visit(node.body, inner, False)
        elif isinstance(node, ast.ClassDef):
            for item in node.decorator_list:
                visit(item, scope, dead)
            bind(scope, node.name, dead)
            typed = scope
            if getattr(node, "type_params", None):
                typed = child("function", f"{node.name}.<type params>", scope)
                bind_params(typed, node)
            inner = child("class", node.name, typed)
            inner.qual = node.name if scope is module else f"{scope.qual}.{node.name}"
            for item in [*node.bases, *node.keywords]:
                visit(item, typed, dead)
            for statement in node.body:
                visit(statement, inner, False)
        elif isinstance(node, _COMPREHENSIONS):
            inner = child("comprehension", type(node).__name__.lower(), scope)
            for index, generator in enumerate(node.generators):
                visit(generator.iter, scope if index == 0 else inner, dead)
                visit(generator.target, inner, False)
                for condition in generator.ifs:
                    visit(condition, inner, False)
            for part in ("elt", "key", "value"):
                if getattr(node, part, None) is not None:
                    visit(getattr(node, part), inner, False)
        elif isinstance(node, ast.NamedExpr):
            target = scope
            while target.kind == "comprehension" and target.parent is not None:
                target = target.parent
            bind(target, node.target.id, dead)
            visit(node.value, scope, dead)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                scope.loads.add(node.id)
            else:
                bind(scope, node.id, dead)
        elif isinstance(node, ast.Global):
            scope.declared_global.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.declared_nonlocal.update(node.names)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    star = True
                else:
                    bind(scope, (alias.asname or alias.name).split(".")[0], dead)
        elif isinstance(node, (ast.If, ast.While)) and _is_dead_test(node.test):
            visit(node.test, scope, dead)
            for statement in node.body:
                visit(statement, scope, True)
            for statement in node.orelse:
                visit(statement, scope, dead)
        else:
            if isinstance(node, ast.ExceptHandler) and node.name:
                bind(scope, node.name, dead)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                bind(scope, node.name, dead)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                bind(scope, node.rest, dead)
            elif type(node).__name__ == "TypeAlias":
                bind(scope, node.name.id, dead)
                inner = child("function", node.name.id, scope)
                bind_params(inner, node)
                visit(node.value, inner, False)
                return
            for sub in ast.iter_child_nodes(node):
                visit(sub, scope, dead)

    for statement in tree.body:
        visit(statement, module, False)
    for scope in scopes[1:]:
        module.stores |= scope.stores & scope.declared_global
    return scopes, star


def _undefined_names(tree: ast.Module, scopes: list[_Scope]) -> set[tuple[str, str]]:
    import builtins

    known = set(dir(builtins)) | _IMPLICIT_NAMES | scopes[0].stores
    undefined: set[tuple[str, str]] = set()
    for scope in scopes:
        for name in scope.loads:
            if name in known or name in scope.declared_nonlocal:
                continue
            if scope.kind != "module" and name in scope.stores and name not in scope.declared_global:
                continue
            outer = scope.parent
            found = False
            while outer is not None and outer.kind != "module":
                if outer.kind != "class" and name in outer.stores and name not in outer.declared_global:
                    found = True
                    break
                outer = outer.parent
            if not found:
                undefined.add((scope.qual, name))
    return undefined


def _unreachable_statements(tree: ast.Module) -> collections.Counter:
    found: collections.Counter = collections.Counter()

    def visit(node: ast.AST, qual: str) -> None:
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if not isinstance(body, list):
                continue
            for index, statement in enumerate(body[:-1]):
                if isinstance(statement, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                    for dead in body[index + 1:]:
                        found[(qual, ast.dump(dead))] += 1
                    break
        for sub in ast.iter_child_nodes(node):
            name = getattr(sub, "name", None)
            inner = f"{qual}.{name}" if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else qual
            visit(sub, inner)

    visit(tree, "<module>")
    return found


def _code_sanity_facts(source: str) -> tuple[set[tuple[str, str]], collections.Counter, bool] | None:
    """Undefined names per scope, statements that can never run, and whether a star import is present."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    scopes, star = _collect_scopes(tree)
    undefined = set() if star else _undefined_names(tree, scopes)
    return undefined, _unreachable_statements(tree), star


def _code_sanity_problems(old: str, new: str) -> list[str]:
    after = _code_sanity_facts(new)
    if after is None:
        return []
    before = (_code_sanity_facts(old) if old else None) or (set(), collections.Counter(), False)
    problems: list[str] = []
    if after[2] and not before[2]:
        problems.append("adds a `from ... import *`, which hides undefined names; import the names you need")
    problems.extend(
        f"uses undefined name `{name}` " + ("at module level" if scope == "<module>" else f"in {scope}")
        for scope, name in sorted(after[0] - before[0])
    )
    if after[1] - before[1]:
        problems.append("adds code after a return, raise, continue or break that can never run")
    return problems


@dataclass(frozen=True)
class CodingProposal:
    title: str
    rationale: str
    files: dict[str, str]
    provider: str


class CodingModule:
    """Bounded software engineering module for Genesis."""

    MAX_CONTEXT_FILES = 4
    MAX_CONTEXT_BYTES = 12_000
    MAX_TEST_CONTEXT_FILES = 2
    MAX_TEST_CONTEXT_BYTES = 4_000
    MAX_FILES = 6
    MAX_TOTAL_BYTES = 80_000
    MAX_EDITS = 1
    MAX_EDIT_BYTES = 4_000
    MAX_PROPOSAL_ATTEMPTS = 3
    MAX_REPAIR_ECHO_BYTES = 2_000
    MAX_LONG_TERM_MEMORY_CHARS = 3_500
    PLACEHOLDER_REPLACEMENTS = frozenset(
        {
            "replacement text",
            "replacement code",
            "new code",
            "code here",
            "insert code here",
            "todo",
            "tbd",
        }
    )

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = root.resolve()
        self.providers = providers or ProviderRegistry()
        self.router = IntelligenceRouter(
            self.providers,
            telemetry_path=self.root / "runtime" / "provider_telemetry.json",
        )
        self.learning = SelfLearningStore(self.root / "runtime" / "self_learning.sqlite3")
        self.memory = GenesisMemory(self.root)
        self.executor = SelfDevelopmentExecutor(self.root)

    def _provider(self):
        try:
            return self.router.select("coding", complexity=0.75, require_non_bootstrap=True).provider
        except RuntimeError:
            pass

        live_candidates = []
        for provider in self.providers.available_providers():
            profile = IntelligenceRouter.profile(provider)
            if profile.name == "genesis-bootstrap":
                continue
            if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            live_candidates.append((profile.resource_cost, -profile.reliability, profile.name, provider))
        if live_candidates:
            live_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            return live_candidates[0][3]

        try:
            return self.router.select("coding", complexity=0.2).provider
        except RuntimeError:
            return None

    def read_context(self, paths: list[str]) -> dict[str, str]:
        context: dict[str, str] = {}
        total = 0
        for relative in paths[: self.MAX_CONTEXT_FILES]:
            normalized = str(relative).replace("\\", "/").lstrip("./")
            self.executor._validate_paths([normalized])
            path = (self.root / normalized).resolve()
            if not path.is_file():
                continue
            data = path.read_bytes()
            remaining = self.MAX_CONTEXT_BYTES - total
            if remaining <= 0:
                break
            text = data[:remaining].decode("utf-8", errors="replace")
            context[normalized] = text
            total += len(text.encode("utf-8"))
        return context

    def _related_test_context(self, paths: list[str]) -> dict[str, str]:
        """Read a small amount of matching test evidence without making tests editable."""
        tests_dir = self.root / "tests"
        if not tests_dir.is_dir():
            return {}
        candidates: list[Path] = []
        for relative in paths:
            normalized = str(relative).replace("\\", "/").lstrip("./")
            source = Path(normalized)
            if not normalized.startswith("genesis/") or source.suffix != ".py":
                continue
            for candidate in sorted(tests_dir.glob(f"test_{source.stem}*.py")):
                if candidate.is_file() and candidate not in candidates:
                    candidates.append(candidate)
                if len(candidates) >= self.MAX_TEST_CONTEXT_FILES:
                    break
            if len(candidates) >= self.MAX_TEST_CONTEXT_FILES:
                break

        context: dict[str, str] = {}
        remaining = self.MAX_TEST_CONTEXT_BYTES
        for candidate in candidates:
            if remaining <= 0:
                break
            relative = candidate.relative_to(self.root).as_posix()
            self.executor._validate_paths([relative])
            data = candidate.read_bytes()[:remaining]
            text = data.decode("utf-8", errors="replace")
            context[relative] = text
            remaining -= len(text.encode("utf-8"))
        return context

    @staticmethod
    def _number_context(text: str) -> str:
        """Expose stable 1-based repository line locators without asking the model to copy source."""
        return "\n".join(f"{index}|{line}" for index, line in enumerate(text.splitlines(), start=1))

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)}

    @classmethod
    def _best_edit_hint(cls, objective: str, context: dict[str, str]) -> tuple[str, int]:
        """Ground the JSON example on the most objective-relevant repository line.

        Small local models often copy schema examples literally. A hard-coded line 1 therefore
        becomes an accidental instruction. Derive the example locator from the actual numbered
        context so copying the example is at least grounded in repository evidence.
        """
        if not context:
            return "", 1
        objective_lower = objective.lower()
        objective_tokens = cls._tokens(objective)
        objective_fragments = tuple(
            fragment.strip()
            for fragment in re.findall(r"`([^`\n]{3,300})`", objective)
            if fragment.strip()
        )
        best: tuple[int, int, int, int, int, str, int] | None = None
        for path_index, (path, text) in enumerate(context.items()):
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                overlap = len(objective_tokens & cls._tokens(stripped))
                exact_bonus = 100 if stripped.lower() in objective_lower else 0
                marker_bonus = 200 if "INSERTION_POINT" in stripped and stripped.lower() in objective_lower else 0
                fragment_bonus = 500 if any(fragment in stripped for fragment in objective_fragments) else 0
                score = overlap + exact_bonus + marker_bonus + fragment_bonus
                rank = (score, marker_bonus, exact_bonus, -path_index, -line_number)
                if best is None or rank > best[:5]:
                    best = (*rank, path, line_number)
        if best is not None:
            return best[5], best[6]
        first_path, first_text = next(iter(context.items()))
        return first_path, max(1, len(first_text.splitlines()))

    @staticmethod
    def _balanced_json_object(text: str) -> str | None:
        start = text.find("{")
        while start >= 0:
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : index + 1]
            start = text.find("{", start + 1)
        return None

    @classmethod
    def _extract_json(cls, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as first_error:
            candidate = cls._balanced_json_object(text)
            if candidate is None:
                raise ValueError(f"provider did not return a complete JSON object: {first_error.msg}") from first_error
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError as nested_error:
                raise ValueError(f"provider returned malformed JSON: {nested_error.msg}") from nested_error
        if not isinstance(value, dict):
            raise ValueError("coding proposal must be a JSON object")
        return value

    @staticmethod
    def _first_nonblank_indent(text: str) -> str:
        for line in text.splitlines():
            if line.strip():
                return line[: len(line) - len(line.lstrip(" \t"))]
        return ""

    @classmethod
    def _normalize_python_replacement(cls, removed: str, replacement: str) -> str:
        """Keep a compact Python line edit at the indentation level it replaces."""
        target_indent = cls._first_nonblank_indent(removed)
        replacement_indent = cls._first_nonblank_indent(replacement)
        if not target_indent or not replacement.strip():
            return replacement
        if len(replacement_indent.expandtabs(8)) >= len(target_indent.expandtabs(8)):
            return replacement
        dedented = textwrap.dedent(replacement)
        return textwrap.indent(dedented, target_indent, predicate=lambda line: bool(line.strip()))

    @staticmethod
    def _has_executable_python_text(text: str) -> bool:
        """Comments and whitespace cannot satisfy a required Python suite body."""
        return any(line.strip() and not line.lstrip().startswith("#") for line in text.splitlines())

    @classmethod
    def _is_placeholder_replacement(cls, text: str) -> bool:
        normalized = " ".join(text.strip().lower().split())
        if normalized in cls.PLACEHOLDER_REPLACEMENTS:
            return True
        return bool(re.fullmatch(r"(?:<|\[)?(?:replacement|insert|new)\s+(?:text|code)(?:>|\])?", normalized))

    @staticmethod
    def _removes_only_python_suite_statement(source: str, start_line: int, end_line: int) -> bool:
        """Detect a line edit that removes the sole statement beneath a retained compound block."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            parent_line = getattr(node, "lineno", None)
            if not isinstance(parent_line, int) or parent_line >= start_line:
                continue
            for field in ("body", "orelse", "finalbody"):
                suite = getattr(node, field, None)
                if not isinstance(suite, list) or len(suite) != 1:
                    continue
                statement = suite[0]
                if not isinstance(statement, ast.stmt):
                    continue
                first = getattr(statement, "lineno", None)
                last = getattr(statement, "end_lineno", first)
                if isinstance(first, int) and isinstance(last, int) and start_line <= first and last <= end_line:
                    return True
        return False

    def _apply_line_edit(
        self, path: str, start_line: object, end_line: object, new: object, current: str | None = None
    ) -> str:
        if not isinstance(start_line, int) or isinstance(start_line, bool):
            raise ValueError("line edit start_line must be an integer")
        if not isinstance(end_line, int) or isinstance(end_line, bool):
            raise ValueError("line edit end_line must be an integer")
        if not isinstance(new, str):
            raise ValueError("line edit new text must be a string")
        if self._is_placeholder_replacement(new):
            raise ValueError("line edit replacement must be real repository code/content, not placeholder text")
        if start_line < 1 or end_line < start_line:
            raise ValueError("line edit range is invalid")

        if current is None:
            current = self._read_edit_target(path)
        lines = current.splitlines(keepends=True)
        if end_line > len(lines):
            raise ValueError(f"line edit range exceeds file length: {path}")

        removed = "".join(lines[start_line - 1 : end_line])
        if path.endswith(".py") and "from __future__ import" in removed and "from __future__ import" not in new:
            raise ValueError("line edit may not overwrite a Python __future__ import")
        if (
            path.endswith(".py")
            and self._removes_only_python_suite_statement(current, start_line, end_line)
            and not self._has_executable_python_text(new)
        ):
            removed_preview = " | ".join(line.strip() for line in removed.splitlines() if line.strip())[:300]
            raise ValueError(
                "Python line edit may not remove the only executable statement from a retained compound block; "
                "provide executable replacement code or choose a different line. "
                f"Rejected range: {path}:{start_line}-{end_line}, which holds the only body statement: {removed_preview!r}. "
                "To add code there, use insert_after_line instead, or keep that statement in new and put the added code before or after it."
            )
        replacement = self._normalize_python_replacement(removed, new) if path.endswith(".py") else new
        if removed.endswith(("\n", "\r")) and replacement and not replacement.endswith(("\n", "\r")):
            replacement += "\n"
        return "".join(lines[: start_line - 1]) + replacement + "".join(lines[end_line:])

    def _read_edit_target(self, path: str) -> str:
        target = (self.root / path).resolve()
        if not target.is_file():
            raise ValueError(f"edit target does not exist: {path}")
        return target.read_text(encoding="utf-8")

    def _apply_insert_edit(self, path: str, after_line: object, new: object, current: str) -> str:
        """Add code after a line without removing anything (0 inserts at the top)."""
        if not isinstance(after_line, int) or isinstance(after_line, bool):
            raise ValueError("insert edit insert_after_line must be an integer")
        if not isinstance(new, str) or not new.strip():
            raise ValueError("insert edit new text must be non-empty code")
        if self._is_placeholder_replacement(new) or new.strip() in {"...", "pass"}:
            raise ValueError("insert edit must be real repository code/content, not placeholder text")
        lines = current.splitlines(keepends=True)
        if after_line < 0 or after_line > len(lines):
            raise ValueError(f"insert edit line is outside the file: {path}")
        if path.endswith(".py"):
            future_lines = [
                index + 1 for index, line in enumerate(lines) if line.lstrip().startswith("from __future__ import")
            ]
            if future_lines and after_line < max(future_lines):
                raise ValueError(
                    f"insert edit in {path} must go after line {max(future_lines)}; "
                    "code cannot be placed above `from __future__` imports"
                )
        # Inserted text keeps the indentation the model wrote. Guessing the
        # block from a neighbouring line can silently move code into or out
        # of an if/def/except body, so the caller states it explicitly.
        inserted = new
        if path.endswith(".py") and after_line and not new[:1].isspace():
            anchor = lines[after_line - 1].split("#", 1)[0].rstrip()
            if anchor.endswith(":") and after_line < len(lines):
                # Only place where the block is certain: right after a line
                # that opens one, code must sit at the body's indentation.
                inserted = self._normalize_python_replacement(lines[after_line], new)
        if not inserted.endswith(("\n", "\r")):
            inserted += "\n"
        if after_line and lines and not lines[after_line - 1].endswith(("\n", "\r")):
            inserted = "\n" + inserted
        return "".join(lines[:after_line]) + inserted + "".join(lines[after_line:])

    def _apply_positioned_edits(self, path: str, edits: list[dict], current: str) -> str:
        """Apply several line/insert edits to one file using the original line numbers.

        Edits are applied bottom-up so earlier edits do not shift later ones,
        and overlapping ranges are rejected instead of guessed.
        """
        spans: list[tuple[int, int, dict]] = []
        for edit in edits:
            if "insert_after_line" in edit:
                if "start_line" in edit or "end_line" in edit:
                    raise ValueError(
                        f"edit in {path} has both insert_after_line and start_line/end_line; use one or the other"
                    )
                after = edit.get("insert_after_line")
                if not isinstance(after, int) or isinstance(after, bool):
                    raise ValueError("insert edit insert_after_line must be an integer")
                spans.append((after + 1, after, edit))
            else:
                start, end = edit.get("start_line"), edit.get("end_line")
                if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
                    raise ValueError("line edit start_line and end_line must be integers")
                spans.append((start, end, edit))
        ordered = sorted(spans, key=lambda row: (row[0], row[1]))
        for (s1, e1, _), (s2, e2, _) in zip(ordered, ordered[1:]):
            if s2 <= max(e1, s1 - 1) or (s1 == s2 and e1 == e2):
                raise ValueError(f"edits overlap in {path}; merge them into one edit")
        rendered = current
        for start, end, edit in sorted(spans, key=lambda row: (row[0], row[1]), reverse=True):
            if "insert_after_line" in edit:
                rendered = self._apply_insert_edit(path, edit.get("insert_after_line"), edit.get("new"), rendered)
            else:
                rendered = self._apply_line_edit(path, start, end, edit.get("new"), current=rendered)
        return rendered

    def _files_from_edits(self, edits: object) -> dict[str, str]:
        if not isinstance(edits, list) or not edits or len(edits) > self.MAX_EDITS:
            raise ValueError("coding proposal edits count out of bounds")
        total = 0
        rendered: dict[str, str] = {}
        positioned: dict[str, list[dict]] = {}
        legacy_paths: set[str] = set()
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("each coding edit must be an object")
            path_value = edit.get("path")
            if not isinstance(path_value, str):
                raise ValueError("each coding edit requires a path")
            path = path_value.replace("\\", "/").lstrip("./")
            self.executor._validate_paths([path])

            if "start_line" in edit or "end_line" in edit or "insert_after_line" in edit:
                new = edit.get("new")
                if isinstance(new, str):
                    total += len(new.encode("utf-8"))
                if total > self.MAX_EDIT_BYTES:
                    raise ValueError("coding proposal edits exceed byte limit")
                if path in legacy_paths:
                    raise ValueError(f"do not mix line edits and old/new edits in {path}")
                positioned.setdefault(path, []).append(edit)
                continue
            if path in positioned:
                raise ValueError(f"do not mix line edits and old/new edits in {path}")
            legacy_paths.add(path)

            old = edit.get("old")
            new = edit.get("new")
            if not isinstance(old, str) or not isinstance(new, str) or not old:
                raise ValueError("coding edit requires start_line/end_line/new or legacy old/new text")
            if self._is_placeholder_replacement(new):
                raise ValueError("coding edit replacement must be real repository code/content, not placeholder text")
            total += len(old.encode("utf-8")) + len(new.encode("utf-8"))
            if total > self.MAX_EDIT_BYTES:
                raise ValueError("coding proposal edits exceed byte limit")
            current = rendered.get(path)
            if current is None:
                target = (self.root / path).resolve()
                if not target.is_file():
                    raise ValueError(f"edit target does not exist: {path}")
                current = target.read_text(encoding="utf-8")
            if current.count(old) != 1:
                raise ValueError(f"edit old text must match exactly once: {path}")
            rendered[path] = current.replace(old, new, 1)
        for path, path_edits in positioned.items():
            rendered[path] = self._apply_positioned_edits(path, path_edits, self._read_edit_target(path))
        return rendered

    @staticmethod
    def _looks_like_single_edit(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        if not isinstance(value.get("path"), str) or not isinstance(value.get("new"), str):
            return False
        line_shape = isinstance(value.get("start_line"), int) and not isinstance(value.get("start_line"), bool)
        line_shape = line_shape and isinstance(value.get("end_line"), int) and not isinstance(value.get("end_line"), bool)
        legacy_shape = isinstance(value.get("old"), str) and bool(value.get("old"))
        insert_shape = isinstance(value.get("insert_after_line"), int) and not isinstance(value.get("insert_after_line"), bool)
        return line_shape or legacy_shape or insert_shape

    @classmethod
    def _normalize_proposal_shape(cls, proposal: dict) -> dict:
        """Recover only narrow, unambiguous one-edit wrappers from small providers."""
        if isinstance(proposal.get("files"), dict):
            return proposal
        edits = proposal.get("edits")
        if isinstance(edits, list):
            return proposal
        if isinstance(edits, dict):
            normalized = dict(proposal)
            normalized["edits"] = [edits]
            return normalized
        edit = proposal.get("edit")
        if isinstance(edit, dict):
            normalized = dict(proposal)
            normalized["edits"] = [edit]
            return normalized
        if cls._looks_like_single_edit(proposal):
            normalized = dict(proposal)
            normalized["edits"] = [
                {
                    key: proposal[key]
                    for key in ("path", "start_line", "end_line", "old", "new")
                    if key in proposal
                }
            ]
            return normalized
        return proposal

    def validate_proposal(self, proposal: dict, provider_name: str) -> CodingProposal:
        if not isinstance(proposal, dict):
            raise ValueError("coding proposal must be a JSON object")
        proposal = self._normalize_proposal_shape(proposal)
        raw_files = proposal.get("files")
        if isinstance(raw_files, dict):
            files = raw_files
        elif "edits" in proposal:
            files = self._files_from_edits(proposal.get("edits"))
        else:
            raise ValueError("coding proposal must contain a files mapping or compact edits list")
        if not files or len(files) > self.MAX_FILES:
            raise ValueError("coding proposal file count out of bounds")
        paths = [str(path) for path in files]
        self.executor._validate_paths(paths)
        total = sum(len(str(content).encode("utf-8")) for content in files.values())
        if total > self.MAX_TOTAL_BYTES:
            raise ValueError("coding proposal exceeds byte limit")
        if not all(isinstance(content, str) for content in files.values()):
            raise ValueError("coding proposal contents must be text")
        current_files: dict[str, str] = {}
        for path in files:
            target = (self.root / str(path)).resolve()
            current_files[str(path)] = target.read_text(encoding="utf-8") if target.is_file() else ""
        run_isolated_review(current_files, {str(path): content for path, content in files.items()})
        for path, content in files.items():
            if str(path).startswith("genesis/architecture_extensions/"):
                validate_architecture_source(content)
            if str(path).endswith(".py"):
                try:
                    ast.parse(content, filename=str(path))
                except SyntaxError as exc:
                    location = f"{exc.lineno}:{exc.offset}" if exc.lineno else "unknown"
                    lines = content.splitlines()
                    center = max(1, exc.lineno or 1)
                    excerpt = "\n".join(
                        f"{index + 1}|{lines[index][:240]}"
                        for index in range(max(0, center - 4), min(len(lines), center + 3))
                    )[:2000]
                    raise ValueError(
                        f"coding proposal creates invalid Python syntax in {path} at {location}: {exc.msg}\n"
                        f"REJECTED_CANDIDATE_CONTEXT (diagnosis only):\n{excerpt}\n"
                        "Candidate line numbers may differ from repository lines. Apply corrections using "
                        "original NUMBERED_CONTEXT coordinates; preserve complete multiline expressions."
                    ) from exc
        python_paths = [str(path) for path in files if str(path).endswith(".py")]
        for path in python_paths:
            problems = _code_sanity_problems(current_files.get(path, ""), files[path])
            if problems:
                raise ValueError(f"coding proposal breaks {path}: " + "; ".join(problems[:5]))
        changed_code = [path for path in python_paths if _changes_code(current_files.get(path, ""), files[path])]
        if (python_paths or not files) and not changed_code:
            raise ValueError(
                "coding proposal only adds or changes comments, docstrings, blank lines, pass or ... placeholders; "
                "it must change real code that fixes the issue"
            )
        return CodingProposal(
            title=str(proposal.get("title", "Genesis bounded coding candidate"))[:200],
            rationale=str(proposal.get("rationale", "one bounded repository edit"))[:4000],
            files={str(path): content for path, content in files.items()},
            provider=provider_name,
        )

    @staticmethod
    def _output_contract() -> str:
        return (
            'Return one JSON object with exactly one "edits" array containing exactly one object. '
            'That edit object must contain "path", integer "start_line", integer "end_line", and string "new". '
            'The "new" value must be the actual repository replacement code/content, never an example or placeholder. '
            'An edit that only adds comments, docstrings, pass or ... is rejected; change real code. '
            'Every name you use must already be defined in that scope, and never leave code after return. '
            'To add new code without replacing any line, use integer "insert_after_line" (0 means the top of the file) '
            'with "new" instead of "start_line"/"end_line"; never send both. Inserted lines are used exactly as written, '
            'so give every inserted line the full leading indentation it needs at that spot in the file '
            '(unindented text right after a line ending in a colon is indented into that block).'
        )

    def _repair_prompt(
        self,
        original_prompt: str,
        raw: str,
        error: Exception,
        attempt: int,
        allowed_paths: tuple[str, ...],
        edit_hint: tuple[str, int],
    ) -> str:
        previous = raw.encode("utf-8", errors="replace")[: self.MAX_REPAIR_ECHO_BYTES].decode("utf-8", errors="replace")
        preferred_path, preferred_line = edit_hint
        if not preferred_path and allowed_paths:
            preferred_path = allowed_paths[0]
        grounded_source_line = ""
        if preferred_path and preferred_line >= 1:
            try:
                source_lines = (self.root / preferred_path).read_text(encoding="utf-8").splitlines()
                if preferred_line <= len(source_lines):
                    grounded_source_line = source_lines[preferred_line - 1]
            except OSError:
                grounded_source_line = ""
        return (
            original_prompt
            + "\nRETRY: previous JSON was invalid. Change strategy using ERROR and repository evidence; do not repeat the rejected edit.\n"
            + f"ERROR: {type(error).__name__}: {str(error)[:3000]}\n"
            + f"PREVIOUS: {previous}\n"
            + f"VALID_PATHS: {json.dumps(allowed_paths)}\n"
            + f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\n"
            + f"GROUNDED_SOURCE_LINE: {grounded_source_line}\n"
            + self._output_contract()
            + " Copy the path exactly from VALID_PATHS/NUMBERED_CONTEXT. Do not invent, summarize, rename, or substitute the path. "
            + "Choose line numbers exactly from NUMBERED_CONTEXT. Exactly one edit. Do not copy old source text unchanged; the only exception is keeping a sole block body statement that your new code is added beside. "
            + "For Python, prefer replacing one complete standalone statement; do not remove the only body of try/except/if/for/while/with/class/def blocks. "
            + "If the defect is inside a Python expression, replace the entire GROUNDED_SOURCE_LINE statement and preserve required leading syntax such as return, raise, assert, or assignment. "
            + "If the selected line is the sole body statement, new must contain executable Python, not only whitespace or comments. To add code without removing lines, use insert_after_line. "
            + "No title, rationale, markdown, commentary, new files, policy changes, test weakening, or protected paths.\n"
        )

    def propose(
        self,
        objective: str,
        context_paths: list[str] | None = None,
        *,
        provider: IntelligenceProvider | None = None,
    ) -> CodingProposal:
        objective = objective.strip()
        if not objective:
            raise ValueError("coding objective is required")
        provider = provider or self._provider()
        if provider is None:
            raise RuntimeError("no intelligence provider available")
        requested_paths = context_paths or []
        context = self.read_context(requested_paths)
        test_context = self._related_test_context(requested_paths)
        numbered_context = {path: self._number_context(text) for path, text in context.items()}
        numbered_test_context = {path: self._number_context(text) for path, text in test_context.items()}
        allowed_paths = tuple(numbered_context)
        edit_hint = self._best_edit_hint(objective, context)
        preferred_path, preferred_line = edit_hint
        if not preferred_path and allowed_paths:
            preferred_path = allowed_paths[0]
            edit_hint = (preferred_path, preferred_line)
        memory_rows = self.memory.recall(objective, limit=4)
        memory_text = json.dumps(memory_rows, sort_keys=True, separators=(",", ":"))
        memory_text = memory_text[: self.MAX_LONG_TERM_MEMORY_CHARS]

        prompt = (
            "ROLE: bounded_coding_engineer\n"
            "TASK: Make exactly ONE smallest useful edit toward OBJECTIVE using only NUMBERED_CONTEXT.\n"
            f"OUTPUT_CONTRACT: {self._output_contract()}\n"
            f"VALID_PATHS: {json.dumps(allowed_paths)}\n"
            f"GROUNDED_LINE_HINT: {preferred_path}:{preferred_line}\n"
            "RULES: exactly one edit; path must match one key from VALID_PATHS exactly; choose 1-based inclusive start_line/end_line from NUMBERED_CONTEXT; do NOT reproduce old source text unchanged, except that when you add code beside the only body statement of a block you must keep that statement in new; "
            "the hint is grounded but must be verified against OBJECTIVE and NUMBERED_CONTEXT; never copy an unrelated example line number; "
            "READ_ONLY_TEST_CONTEXT is evidence for expected behavior only and can never be an edit target; never weaken or rewrite tests to make a candidate pass; "
            "never emit placeholder path or replacement text; no title/rationale/markdown/explanation; do not create files. The local executor resolves those lines against the repository and preserves local Python indentation. "
            "For Python, replace a complete standalone statement rather than deleting the only body of a compound block; a sole body replacement must contain executable code, not only comments or whitespace. "
            "Allowed path prefixes: genesis/, tests/, docs/, config/, desktop/, mobile/. Never change Constitution, Genesis Block, .github, validation/quorum, permissions, secrets, or weaken tests.\n"
            f"OBJECTIVE: {objective}\n"
            f"NUMBERED_CONTEXT: {json.dumps(numbered_context, sort_keys=True)}\n"
            f"READ_ONLY_TEST_CONTEXT: {json.dumps(numbered_test_context, sort_keys=True)}\n"
            "VALIDATED_LONG_TERM_MEMORY_POLICY: Memory is prior evidence, not current truth or authority. "
            "Use it to avoid repeated failed approaches, but verify every lesson against OBJECTIVE, NUMBERED_CONTEXT, "
            "READ_ONLY_TEST_CONTEXT, and current validation. Ignore a remembered fix when current repository evidence conflicts.\n"
            f"VALIDATED_LONG_TERM_MEMORY: {memory_text}\n"
        )
        current_prompt = prompt
        last_error: Exception | None = None
        last_raw = ""
        for attempt in range(1, self.MAX_PROPOSAL_ATTEMPTS + 1):
            raw = ""
            try:
                raw = provider.reason(current_prompt)
                return self.validate_proposal(self._extract_json(raw), provider.name)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                last_raw = raw
                if attempt >= self.MAX_PROPOSAL_ATTEMPTS:
                    break
                current_prompt = self._repair_prompt(prompt, raw, exc, attempt, allowed_paths, edit_hint)
        failure = ValueError(
            f"coding provider failed to produce a valid proposal after {self.MAX_PROPOSAL_ATTEMPTS} bounded attempts: {last_error}"
        )
        # Keep the rejected proposal so the next strategy can see what not to repeat.
        failure.rejected_change = str(last_raw or "")[: self.MAX_REPAIR_ECHO_BYTES]  # type: ignore[attr-defined]
        raise failure

    def execute_candidate(self, proposal: CodingProposal) -> SelfDevResult:
        payload = {
            "title": proposal.title,
            "rationale": proposal.rationale,
            "files": proposal.files,
        }
        return self.executor.execute(payload)

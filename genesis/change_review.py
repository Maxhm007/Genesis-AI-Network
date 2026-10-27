"""Independent safety review of every change the solver proposes (#1128).

This reviewer is deliberately not an AI model and is a protected path, so the
solver can neither talk it into approving a change nor rewrite it. It compares
each proposed file with the current file and rejects changes that *add*:

- network, process, native-code or deserialisation capabilities,
- dynamic code execution (eval, exec, compile, __import__, os.system),
- credential-looking values,
- new hard-coded URLs,
- text that tries to instruct an AI (prompt injection),
- removal of a call to Genesis's own safety helpers.

Anything already in the file is left alone, so existing code keeps working.
A rejection raises ValueError, which the solver treats like any other invalid
proposal and retries with the findings as feedback.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from .log_redaction import redact_secrets

RISKY_MODULES = frozenset({
    "socket", "ssl", "requests", "httpx", "aiohttp", "urllib", "urllib3", "http", "ftplib", "smtplib",
    "telnetlib", "paramiko", "subprocess", "ctypes", "cffi", "pickle", "marshal", "shelve", "dill",
    "importlib", "builtins", "multiprocessing", "pty", "asyncio",
})
RISKY_CALLS = frozenset({
    "eval", "exec", "compile", "__import__",
    "os.system", "os.popen", "os.execv", "os.execve", "os.spawnv", "os.fork",
    "subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
    "importlib.import_module",
    # Bare names catch aliased or from-imported forms such as `from os import system`.
    *(f"os.{name}" for name in (
        "popen", "fork", "forkpty", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe",
        "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
    )),
    "subprocess.getoutput", "subprocess.getstatusoutput", "pty.spawn",
    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
    # A plain call such as system(...) with no import is still treated as risky.
    "system", "popen", "import_module",
    "getattr-on-module", "setattr-on-module", "sys.modules",
    *(f"star-import:{module}" for module in ("os", "posix", "subprocess", "importlib", "builtins", "pty", "ctypes")),
})
SAFETY_CALLS = frozenset({
    "redact_secrets", "is_automation_comment", "trusted_comments", "_validate_paths",
    "normalize_selfdev_path", "review_change", "enforce_review", "run_isolated_review",
})
URL_RE = re.compile(r"\b(?:https?|ftp|wss?)://[^\s'\"]+", re.IGNORECASE)
INJECTION_RE = re.compile(
    r"(?i)\b(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)"
    r"|disregard (?:the |all )?(?:rules|instructions)"
    r"|you are now\b|system prompt|developer mode|jailbreak"
    r"|approve this (?:change|candidate)|mark (?:this|it) as verified)"
)


@dataclass(frozen=True)
class ReviewFinding:
    path: str
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _python_facts(source: str) -> dict[str, set[str]] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    facts: dict[str, set[str]] = {"modules": set(), "calls": set(), "safety": set(), "patches": set(), "strings": set()}
    aliases: dict[str, str] = {}
    module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts["modules"].add(alias.name.split(".")[0])
                if alias.asname:
                    aliases[alias.asname] = alias.name
                module_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            facts["modules"].add(node.module.split(".")[0])
            for alias in node.names:
                if alias.name == "*":
                    facts["calls"].add(f"star-import:{node.module}")
                    continue
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for node in ast.walk(tree):
        # `o = os` makes o another name for the module.
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
            source = _dotted(node.value)
            head = source.partition(".")[0]
            if head in module_names or head in aliases:
                resolved_source = aliases.get(head, head) + source[len(head):]
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = resolved_source
                        module_names.add(target.id)
        if isinstance(node, ast.Attribute) and _dotted(node).startswith("sys.modules"):
            facts["calls"].add("sys.modules")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name:
                head, _, rest = name.partition(".")
                resolved = aliases.get(head, head) + (f".{rest}" if rest else "")
                facts["calls"].update({name, resolved})
                facts["safety"].update({name.rsplit(".", 1)[-1], resolved.rsplit(".", 1)[-1]})
                if name in {"getattr", "setattr"} and node.args:
                    target = _dotted(node.args[0]).partition(".")[0]
                    if target in module_names or target in aliases:
                        facts["calls"].add(f"{name}-on-module")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute):
                    root: ast.AST = target
                    while isinstance(root, (ast.Attribute, ast.Subscript, ast.Call)):
                        root = root.func if isinstance(root, ast.Call) else root.value
                    head = root.id if isinstance(root, ast.Name) else ""
                    if head in module_names or head in aliases:
                        facts["patches"].add(ast.unparse(target))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            facts["strings"].add(node.value)
    return facts


def _text_facts(text: str) -> dict[str, set[str]]:
    return {
        "urls": set(URL_RE.findall(text)),
        "injection": {match.group(0).lower() for match in INJECTION_RE.finditer(text)},
    }


def _added_lines(old: str, new: str) -> str:
    before = set(old.splitlines())
    return "\n".join(line for line in new.splitlines() if line not in before)


def review_change(path: str, old: str, new: str) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    added = _added_lines(old, new)

    if redact_secrets(added, environ={}) != added:
        findings.append(ReviewFinding(path, "credential", "adds a value that looks like a secret or token"))

    old_text, new_text = _text_facts(old), _text_facts(new)
    for url in sorted(new_text["urls"] - old_text["urls"]):
        findings.append(ReviewFinding(path, "new-url", f"adds hard-coded URL {url[:120]}"))
    for phrase in sorted(new_text["injection"] - old_text["injection"]):
        findings.append(ReviewFinding(path, "prompt-injection", f"adds instruction-like text {phrase!r}"))

    if path.endswith(".py"):
        before = _python_facts(old) or {"modules": set(), "calls": set(), "safety": set(), "patches": set(), "strings": set()}
        after = _python_facts(new)
        if after is not None:
            for module in sorted((after["modules"] - before["modules"]) & RISKY_MODULES):
                findings.append(ReviewFinding(path, "risky-import", f"adds import of {module}"))
            for call in sorted((after["calls"] - before["calls"]) & RISKY_CALLS):
                findings.append(ReviewFinding(path, "risky-call", f"adds call to {call}"))
            for patched in sorted(after["patches"] - before["patches"]):
                findings.append(ReviewFinding(path, "module-patch", f"assigns to imported module attribute {patched}"))
            for call in sorted((before["safety"] - after["safety"]) & SAFETY_CALLS):
                findings.append(ReviewFinding(path, "safety-removed", f"removes call to {call}"))
    return findings


def review_files(current: dict[str, str], proposed: dict[str, str]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for path, content in proposed.items():
        findings.extend(review_change(path, current.get(path, ""), content))
    return findings


def enforce_review(current: dict[str, str], proposed: dict[str, str]) -> None:
    findings = review_files(current, proposed)
    if findings:
        details = "; ".join(finding.render() for finding in findings[:8])
        raise ValueError(
            "independent change review rejected this proposal: " + details
            + ". Solve the objective without adding these capabilities or removing safety checks."
        )

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from genesis.coding import CodingModule
from genesis.providers import IntelligenceProvider, ProviderRegistry
from genesis.selfdev import SelfDevelopmentExecutor, SelfDevResult

from .workspace import EditProposal, LabSnapshot, LabWorkspace


RETRY_METHODS = (
    "correctness",
    "edge_cases",
    "failure_analysis",
    "simplification",
    "fresh_approach",
)


class TargetGroundedProvider:
    """Constrain one provider call to DevLab's already-authorized target path.

    The adapter grounds only schema placeholders already present in the coding
    contract and gives a bounded second chance when a small model copies example
    content instead of designing code. It never invents the source change itself,
    expands allowed paths, or bypasses CodingModule/DevLab validation.
    """

    PATH_PLACEHOLDER_RE = re.compile(r'("path"\s*:\s*)"existing allowed path"')
    CONTENT_PLACEHOLDER_RE = re.compile(r'("new"\s*:\s*)"replacement text"')
    MAX_CONTENT_REPROMPTS = 2

    def __init__(self, provider: IntelligenceProvider, target_path: str) -> None:
        self.provider = provider
        self.target_path = target_path.replace("\\", "/").lstrip("./")
        self.name = provider.name

    def available(self) -> bool:
        return self.provider.available()

    def _prepare_prompt(self, prompt: str) -> str:
        # A schema-only null is intentionally invalid as a final edit value. If a
        # provider copies it, CodingModule rejects it and uses its bounded repair
        # cycle instead of executing meaningless source text.
        prompt = self.CONTENT_PLACEHOLDER_RE.sub(r"\1null", prompt)
        return (
            prompt
            + "\nDEVLAB_EXACT_TARGET_PATH: "
            + self.target_path
            + "\nFor the JSON edit path, use exactly DEVLAB_EXACT_TARGET_PATH. "
            + "The JSON field new MUST be a non-empty string containing the actual source code you design to solve OBJECTIVE. "
            + "Do not copy schema labels or example content into new.\n"
        )

    def _ground_path(self, raw: str) -> str:
        replacement = r"\1" + json.dumps(self.target_path)
        return self.PATH_PLACEHOLDER_RE.sub(replacement, raw)

    def reason(self, prompt: str) -> str:
        grounded_prompt = self._prepare_prompt(prompt)
        raw = ""
        for content_attempt in range(self.MAX_CONTENT_REPROMPTS + 1):
            retry_note = ""
            if content_attempt:
                retry_note = (
                    "\nDEVLAB_CONTENT_RETRY: The previous response copied schema/example content instead of solving the task. "
                    "Re-read OBJECTIVE and NUMBERED_CONTEXT. Return actual replacement source code in new; keep exactly one bounded edit.\n"
                )
            raw = self._ground_path(self.provider.reason(grounded_prompt + retry_note))
            if not self.CONTENT_PLACEHOLDER_RE.search(raw):
                return raw

        # Never let literal schema content reach the source tree. Converting only
        # the known placeholder to null makes the normal CodingModule validator
        # reject it and enter its own bounded repair path.
        return self.CONTENT_PLACEHOLDER_RE.sub(r"\1null", raw)


@dataclass(frozen=True)
class InspectionReport:
    path: str
    syntax_ok: bool
    line_count: int
    functions: tuple[str, ...]
    classes: tuple[str, ...]
    imports: tuple[str, ...]
    todo_markers: int


@dataclass(frozen=True)
class RetryPlan:
    attempt: int
    method: str
    previous_error: str = ""
    exhausted: bool = False


@dataclass(frozen=True)
class TestResult:
    passed: bool
    returncode: int
    output: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class ValidationFeedback:
    candidate_created: bool
    tests_passed: bool
    commit_sha: str | None
    branch: str
    failure: str


@dataclass(frozen=True)
class DevLabAttempt:
    target_path: str
    problem: str
    acceptance: str
    inspection: InspectionReport
    snapshot: LabSnapshot
    retry: RetryPlan
    lab_candidate_path: str | None
    feedback: ValidationFeedback | None
    status: str

    def as_dict(self) -> dict:
        return asdict(self)


class GenesisDevLab:
    """Bounded headless development workbench for Genesis.

    DevLab can inspect/search source, create isolated snapshots, request one-file
    edits, run pytest, rotate retry methods, and hand an exact candidate to the
    existing self-development executor. It cannot approve validation or write
    directly to ``main``.
    """

    MAX_TEST_OUTPUT = 6000

    def __init__(self, root: str | Path, providers: ProviderRegistry | None = None) -> None:
        self.root = Path(root).resolve()
        self.workspace = LabWorkspace(self.root)
        self.coding = CodingModule(self.root, providers)
        self.executor = SelfDevelopmentExecutor(self.root)

    def inspect(self, target_path: str) -> InspectionReport:
        text = self.workspace.read(target_path)
        try:
            tree = ast.parse(text, filename=target_path)
        except SyntaxError:
            return InspectionReport(target_path, False, len(text.splitlines()), (), (), (), text.lower().count("todo"))
        functions = tuple(node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
        classes = tuple(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        return InspectionReport(
            target_path,
            True,
            len(text.splitlines()),
            functions,
            classes,
            tuple(imports),
            text.lower().count("todo"),
        )

    def search_text(self, needle: str, *, max_results: int = 25) -> tuple[str, ...]:
        if not needle.strip():
            return ()
        results: list[str] = []
        for base in (self.root / "genesis", self.root / "tests"):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue
                for lineno, line in enumerate(lines, 1):
                    if needle in line:
                        results.append(f"{path.relative_to(self.root)}:{lineno}:{line.strip()}")
                        if len(results) >= max_results:
                            return tuple(results)
        return tuple(results)

    @staticmethod
    def retry_plan(attempt: int, previous_error: str = "", *, max_attempts: int = 5) -> RetryPlan:
        max_attempts = max(1, min(int(max_attempts), len(RETRY_METHODS)))
        attempt = max(0, int(attempt))
        exhausted = attempt >= max_attempts
        index = min(attempt, max_attempts - 1)
        return RetryPlan(
            attempt=attempt + 1,
            method=RETRY_METHODS[index],
            previous_error=str(previous_error)[-2000:],
            exhausted=exhausted,
        )

    @staticmethod
    def feedback_from_result(result: SelfDevResult) -> ValidationFeedback:
        return ValidationFeedback(
            candidate_created=bool(result.committed and result.commit_sha),
            tests_passed=bool(result.tests_passed),
            commit_sha=result.commit_sha,
            branch=result.branch,
            failure="" if result.tests_passed and result.committed else str(result.message or "candidate did not complete")[-2000:],
        )

    def run_tests(self, targets: tuple[str, ...] = (), *, timeout_seconds: int = 180) -> TestResult:
        timeout_seconds = max(5, min(int(timeout_seconds), 600))
        command = (sys.executable, "-m", "pytest", "-q", *targets)
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
            output = (result.stdout + "\n" + result.stderr)[-self.MAX_TEST_OUTPUT :]
            return TestResult(result.returncode == 0, result.returncode, output, command)
        except subprocess.TimeoutExpired as exc:
            return TestResult(False, 124, f"pytest timed out after {timeout_seconds}s: {exc}"[-self.MAX_TEST_OUTPUT :], command)

    def attempt_problem(
        self,
        *,
        target_path: str,
        problem: str,
        acceptance: str,
        attempt: int = 0,
        previous_error: str = "",
        provider: IntelligenceProvider | None = None,
        provenance: dict | None = None,
    ) -> DevLabAttempt:
        inspection = self.inspect(target_path)
        snapshot = self.workspace.snapshot(target_path)
        retry = self.retry_plan(attempt, previous_error)
        if retry.exhausted:
            return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, None, None, "retry_exhausted")

        objective = (
            f"DEVLAB TARGET: {target_path}. PROBLEM: {problem}. ACCEPTANCE: {acceptance}. "
            f"METHOD: {retry.method}. PREVIOUS_FAILURE: {retry.previous_error or 'none'}. "
            "Diagnose the target and make exactly one smallest useful edit to that target only. "
            "Do not weaken tests, security, validation, governance, or promotion boundaries."
        )
        grounded_provider = TargetGroundedProvider(provider, target_path) if provider is not None else None
        try:
            proposal = self.coding.propose(objective, context_paths=[target_path], provider=grounded_provider)
        except Exception as exc:
            feedback = ValidationFeedback(False, False, None, "", f"proposal failed: {type(exc).__name__}: {exc}"[-2000:])
            return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, None, feedback, "proposal_failed")

        normalized = target_path.replace("\\", "/").lstrip("./")
        if set(proposal.files) != {normalized}:
            feedback = ValidationFeedback(False, False, None, "", "proposal attempted to edit outside the assigned target")
            return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, None, feedback, "proposal_rejected")

        content = proposal.files[normalized]
        lab_path = self.workspace.stage_edit(snapshot, EditProposal(normalized, content, proposal.rationale))
        result = self.executor.execute(
            {
                "title": f"DevLab: {problem[:120]}",
                "rationale": proposal.rationale,
                "files": {normalized: content},
                "provenance": dict(provenance or {"initiator": "genesis.devlab", "designer": "genesis.devlab"}),
            }
        )
        feedback = self.feedback_from_result(result)
        status = "candidate_created" if feedback.candidate_created and feedback.tests_passed else "candidate_failed"
        return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, lab_path, feedback, status)

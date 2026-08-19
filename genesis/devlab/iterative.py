from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from genesis.coding import CodingModule
from genesis.providers import IntelligenceProvider, ProviderRegistry

from .module import DevLabAttempt, GenesisDevLab, TargetGroundedProvider, ValidationFeedback
from .workspace import EditProposal


class IterativeGenesisDevLab(GenesisDevLab):
    """DevLab with an IDE-like bounded edit/test/revise loop.

    Candidate experimentation happens in a disposable detached Git worktree. A
    failed trial is fed back to the same provider while the provider sees the
    already-modified target file. Only a test-passing final source snapshot is
    handed to SelfDevelopmentExecutor, so failed experiments never become
    promotable candidate branches.

    Owner-assigned challenges may also supply bounded ephemeral acceptance tests.
    Those files exist only inside the disposable worktree and can therefore expose
    a known defect without placing a failing test on ``main``. They are never
    copied into the candidate; the normal candidate gate still requires the final
    source edit to pass the repository's ordinary full suite.
    """

    MAX_INNER_REVISIONS = 3
    MAX_INNER_FAILURE_BYTES = 4000
    MAX_EPHEMERAL_FILES = 4
    MAX_EPHEMERAL_BYTES = 24_000

    def __init__(self, root: str | Path, providers: ProviderRegistry | None = None) -> None:
        super().__init__(root, providers)

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.root,
            text=True,
            capture_output=True,
            check=check,
        )

    def _add_worktree(self, destination: Path) -> None:
        self._git("worktree", "add", "--detach", str(destination), "HEAD")

    def _remove_worktree(self, destination: Path) -> None:
        self._git("worktree", "remove", "--force", str(destination), check=False)
        self._git("worktree", "prune", check=False)

    @classmethod
    def _install_ephemeral_files(cls, worktree: Path, files: dict[str, str] | None) -> tuple[str, ...]:
        if not files:
            return ()
        if len(files) > cls.MAX_EPHEMERAL_FILES:
            raise ValueError("too many ephemeral acceptance files")

        installed: list[str] = []
        total_bytes = 0
        for raw_path, raw_content in files.items():
            path = str(raw_path).replace("\\", "/")
            candidate = PurePosixPath(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"invalid ephemeral acceptance path: {path}")
            normalized = candidate.as_posix().lstrip("./")
            if not normalized.startswith("tests/test_") or not normalized.endswith(".py"):
                raise ValueError("ephemeral acceptance files must be Python tests under tests/test_*.py")
            content = str(raw_content)
            total_bytes += len(content.encode("utf-8"))
            if total_bytes > cls.MAX_EPHEMERAL_BYTES:
                raise ValueError("ephemeral acceptance files exceed bounded size")
            target = worktree / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            installed.append(normalized)
        return tuple(installed)

    def _trial_tests(self, worktree: Path, *, timeout_seconds: int = 180) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=worktree,
                text=True,
                capture_output=True,
                timeout=max(5, min(int(timeout_seconds), 600)),
            )
            output = (result.stdout + "\n" + result.stderr)[-self.MAX_TEST_OUTPUT :]
            return result.returncode == 0, output
        except subprocess.TimeoutExpired as exc:
            return False, f"pytest timed out: {exc}"[-self.MAX_TEST_OUTPUT :]

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
        ephemeral_files: dict[str, str] | None = None,
    ) -> DevLabAttempt:
        inspection = self.inspect(target_path)
        snapshot = self.workspace.snapshot(target_path)
        retry = self.retry_plan(attempt, previous_error)
        if retry.exhausted:
            return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, None, None, "retry_exhausted")

        normalized = target_path.replace("\\", "/").lstrip("./")
        final_content: str | None = None
        last_failure = retry.previous_error

        with tempfile.TemporaryDirectory(prefix="genesis-devlab-") as temp_dir:
            worktree = Path(temp_dir) / "repo"
            self._add_worktree(worktree)
            try:
                installed_acceptance = self._install_ephemeral_files(worktree, ephemeral_files)
                worktree_coding = CodingModule(worktree, self.coding.providers)
                grounded_provider = TargetGroundedProvider(provider, normalized) if provider is not None else None

                for revision in range(1, self.MAX_INNER_REVISIONS + 1):
                    acceptance_signal = (
                        ", ".join(installed_acceptance) if installed_acceptance else "repository test suite only"
                    )
                    objective = (
                        f"DEVLAB TARGET: {normalized}. PROBLEM: {problem}. ACCEPTANCE: {acceptance}. "
                        f"METHOD: {retry.method}. INNER_REVISION: {revision}/{self.MAX_INNER_REVISIONS}. "
                        f"EXECUTABLE_ACCEPTANCE: {acceptance_signal}. "
                        f"PREVIOUS_TEST_FAILURE: {last_failure or 'none'}. "
                        "Inspect the current target state, diagnose the failure, and make exactly one smallest useful edit. "
                        "The current target may already contain a failed earlier revision, so repair it rather than restarting blindly. "
                        "Do not weaken tests, security, validation, governance, or promotion boundaries."
                    )
                    try:
                        proposal = worktree_coding.propose(
                            objective,
                            context_paths=[normalized],
                            provider=grounded_provider,
                        )
                    except Exception as exc:
                        last_failure = f"proposal failed: {type(exc).__name__}: {exc}"[-self.MAX_INNER_FAILURE_BYTES :]
                        continue

                    if set(proposal.files) != {normalized}:
                        last_failure = "proposal attempted to edit outside the assigned target"
                        continue

                    content = proposal.files[normalized]
                    target = worktree / normalized
                    target.write_text(content, encoding="utf-8")
                    passed, output = self._trial_tests(worktree)
                    if passed:
                        final_content = target.read_text(encoding="utf-8")
                        break
                    last_failure = output[-self.MAX_INNER_FAILURE_BYTES :]
            finally:
                self._remove_worktree(worktree)

        if final_content is None:
            feedback = ValidationFeedback(False, False, None, "", last_failure or "bounded DevLab revisions exhausted")
            return DevLabAttempt(
                target_path,
                problem,
                acceptance,
                inspection,
                snapshot,
                retry,
                None,
                feedback,
                "iterative_trials_failed",
            )

        lab_path = self.workspace.stage_edit(snapshot, EditProposal(normalized, final_content, "validated iterative DevLab trial"))
        result = self.executor.execute(
            {
                "title": f"DevLab: {problem[:120]}",
                "rationale": "bounded inspect-edit-test-revise loop produced a test-passing source snapshot",
                "files": {normalized: final_content},
                "provenance": dict(provenance or {"initiator": "genesis.devlab", "designer": "genesis.devlab"}),
            }
        )
        feedback = self.feedback_from_result(result)
        status = "candidate_created" if feedback.candidate_created and feedback.tests_passed else "candidate_failed"
        return DevLabAttempt(target_path, problem, acceptance, inspection, snapshot, retry, lab_path, feedback, status)

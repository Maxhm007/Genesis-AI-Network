from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .workspace import EditProposal, LabWorkspace


@dataclass(frozen=True)
class CodeOSSSession:
    session_id: str
    workspace_path: str
    allowed_paths: tuple[str, ...]
    code_oss_path: str
    launch_command: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CodeOSSTestResult:
    passed: bool
    returncode: int
    output: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CodeOSSSubmission:
    session_id: str
    target_path: str
    lab_candidate_path: str
    candidate_created: bool
    tests_passed: bool
    commit_sha: str | None
    branch: str
    failure: str


class CodeOSSBridge:
    """Bounded Code - OSS workspace adapter for Genesis DevLab.

    Code - OSS never receives the canonical repository as its writable workspace.
    DevLab creates an isolated working copy under ``runtime/`` and only imports
    edits from explicitly authorized paths. Promotion remains owned by the
    existing self-development and validator pipeline.
    """

    SUBMODULE_RELATIVE_PATH = "vendor/code-oss"
    MAX_TEST_OUTPUT = 6000
    COPY_IGNORES = (
        ".git",
        ".genesis",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "runtime",
        "state",
        "vendor",
        "venv",
    )

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.workspace = LabWorkspace(self.root)
        self.session_root = self.root / "runtime" / "task_reviews" / "devlab" / "code_oss"
        self.submodule_path = self.root / self.SUBMODULE_RELATIVE_PATH

    def available(self) -> bool:
        """Return whether the Code - OSS submodule is initialized enough to launch."""
        return (self.submodule_path / "package.json").is_file()

    def _normalize_source_path(self, relative: str) -> str:
        source = self.workspace.resolve_source(relative)
        return str(source.relative_to(self.root)).replace("\\", "/")

    def _code_command(self) -> tuple[str, ...]:
        override = os.getenv("GENESIS_CODE_OSS_COMMAND", "").strip()
        if override:
            parsed = tuple(shlex.split(override))
            if not parsed:
                raise ValueError("GENESIS_CODE_OSS_COMMAND must contain an executable")
            return parsed
        script = "code.bat" if os.name == "nt" else "code.sh"
        return (str(self.submodule_path / "scripts" / script),)

    def create_session(self, allowed_paths: tuple[str, ...]) -> CodeOSSSession:
        """Create a writable isolated repository copy for one bounded DevLab task."""
        normalized = tuple(dict.fromkeys(self._normalize_source_path(path) for path in allowed_paths))
        if not normalized:
            raise ValueError("Code - OSS session requires at least one authorized path")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        session_id = f"{stamp}-{secrets.token_hex(4)}"
        session_dir = self.session_root / session_id
        workspace_dir = session_dir / "workspace"
        session_dir.mkdir(parents=True, exist_ok=False)

        shutil.copytree(
            self.root,
            workspace_dir,
            ignore=shutil.ignore_patterns(*self.COPY_IGNORES),
        )

        command = (*self._code_command(), str(workspace_dir))
        session = CodeOSSSession(
            session_id=session_id,
            workspace_path=str(workspace_dir.relative_to(self.root)).replace("\\", "/"),
            allowed_paths=normalized,
            code_oss_path=self.SUBMODULE_RELATIVE_PATH,
            launch_command=command,
        )
        manifest = {
            **session.as_dict(),
            "direct_main_write": False,
            "validation_authority": False,
            "protected_file_bypass": False,
            "candidate_import_only": True,
        }
        (workspace_dir / ".genesis-code-oss-session.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return session

    def workspace_for(self, session: CodeOSSSession) -> Path:
        path = (self.root / session.workspace_path).resolve()
        try:
            path.relative_to(self.session_root.resolve())
        except ValueError as exc:
            raise ValueError("Code - OSS session escapes DevLab runtime") from exc
        if not path.is_dir():
            raise FileNotFoundError(session.workspace_path)
        return path

    def launch(self, session: CodeOSSSession) -> subprocess.Popen:
        """Launch Code - OSS on the isolated session, never on canonical ``main``."""
        if not self.available():
            raise FileNotFoundError(
                "Code - OSS submodule is not initialized; run git submodule update --init --recursive"
            )
        workspace = self.workspace_for(session)
        command = (*self._code_command(), str(workspace))
        return subprocess.Popen(command, cwd=self.submodule_path)

    def candidate_proposal(
        self,
        session: CodeOSSSession,
        target_path: str,
        *,
        rationale: str = "Code - OSS DevLab candidate",
    ) -> EditProposal:
        """Import exactly one authorized edited file from the isolated IDE session."""
        normalized = self._normalize_source_path(target_path)
        if normalized not in session.allowed_paths:
            raise PermissionError("Code - OSS candidate path was not authorized for this DevLab session")

        workspace = self.workspace_for(session)
        candidate_path = (workspace / normalized).resolve()
        try:
            candidate_path.relative_to(workspace)
        except ValueError as exc:
            raise ValueError("Code - OSS candidate path escapes isolated workspace") from exc
        if not candidate_path.is_file():
            raise FileNotFoundError(normalized)

        content = candidate_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError("Code - OSS candidate content must not be empty")
        original = self.workspace.read(normalized)
        if content == original:
            raise ValueError("Code - OSS session did not change the authorized target")

        return EditProposal(normalized, content, rationale)

    def run_tests(
        self,
        session: CodeOSSSession,
        targets: tuple[str, ...] = (),
        *,
        timeout_seconds: int = 180,
    ) -> CodeOSSTestResult:
        """Run only the bounded pytest command inside the isolated IDE workspace."""
        timeout_seconds = max(5, min(int(timeout_seconds), 600))
        command = (sys.executable, "-m", "pytest", "-q", *targets)
        workspace = self.workspace_for(session)
        try:
            result = subprocess.run(
                command,
                cwd=workspace,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
            output = (result.stdout + "\n" + result.stderr)[-self.MAX_TEST_OUTPUT :]
            return CodeOSSTestResult(result.returncode == 0, result.returncode, output, command)
        except subprocess.TimeoutExpired as exc:
            return CodeOSSTestResult(
                False,
                124,
                f"pytest timed out after {timeout_seconds}s: {exc}"[-self.MAX_TEST_OUTPUT :],
                command,
            )

    def submit_candidate(
        self,
        devlab,
        session: CodeOSSSession,
        target_path: str,
        *,
        problem: str,
        rationale: str = "Code - OSS DevLab candidate",
        provenance: dict | None = None,
    ) -> CodeOSSSubmission:
        """Route an IDE edit back through DevLab's existing candidate pipeline.

        The bridge does not commit to ``main``. It snapshots the canonical target,
        stages the isolated IDE content as a DevLab candidate, and delegates to
        ``SelfDevelopmentExecutor`` so the normal tests/validation/promotion
        boundaries remain authoritative.
        """
        proposal = self.candidate_proposal(session, target_path, rationale=rationale)
        snapshot = devlab.workspace.snapshot(proposal.target_path)
        lab_candidate_path = devlab.workspace.stage_edit(snapshot, proposal)
        result = devlab.executor.execute(
            {
                "title": f"Code OSS DevLab: {problem[:120]}",
                "rationale": proposal.rationale,
                "files": {proposal.target_path: proposal.content},
                "provenance": dict(
                    provenance
                    or {
                        "initiator": "genesis.devlab.code_oss",
                        "designer": "genesis.devlab.code_oss",
                    }
                ),
            }
        )
        feedback = devlab.feedback_from_result(result)
        return CodeOSSSubmission(
            session_id=session.session_id,
            target_path=proposal.target_path,
            lab_candidate_path=lab_candidate_path,
            candidate_created=feedback.candidate_created,
            tests_passed=feedback.tests_passed,
            commit_sha=feedback.commit_sha,
            branch=feedback.branch,
            failure=feedback.failure,
        )

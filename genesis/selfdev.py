from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PROTECTED_PATHS = {
    "GENESIS_CONSTITUTION.md",
    "GENESIS_BLOCK.json",
}

ALLOWED_PREFIXES = (
    "genesis/",
    "tests/",
    "docs/",
    "config/",
    "desktop/",
    "mobile/",
)


def normalize_selfdev_path(root: Path, path: str) -> str:
    """Return a canonical allowed repository-relative path or reject it.

    Provider/model output is untrusted. Prefix checks alone are insufficient
    because `genesis/../.git/...` still begins with an allowed prefix while the
    filesystem resolves it outside that sandbox. Reject traversal, absolute
    paths, Git metadata, protected identity files, and symlink escapes before
    any file is written or tests are executed.
    """
    root = root.resolve()
    raw = str(path).replace("\\", "/")
    if not raw or "\x00" in raw:
        raise RuntimeError("invalid self-development path")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError(f"path traversal is forbidden: {raw}")
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        raise RuntimeError("invalid self-development path")
    if normalized in PROTECTED_PATHS:
        raise RuntimeError(f"protected path cannot be changed: {normalized}")
    if normalized == ".git" or normalized.startswith(".git/"):
        raise RuntimeError("self-development may not modify Git metadata")
    if normalized.startswith(".github/"):
        raise RuntimeError("self-development may not modify GitHub workflow permissions")
    if not normalized.startswith(ALLOWED_PREFIXES):
        raise RuntimeError(f"path outside self-development sandbox: {normalized}")

    target = root.joinpath(*candidate.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"path outside repository root: {normalized}") from exc
    return normalized


@dataclass(frozen=True)
class SelfDevResult:
    branch: str
    candidate_id: str
    tests_passed: bool
    committed: bool
    changed_files: tuple[str, ...]
    commit_sha: str | None
    message: str


class SelfDevelopmentExecutor:
    """Bounded self-development engine.

    It may create or modify files only inside explicitly allowed paths, never
    touches the Genesis Constitution or Genesis Block, always runs tests before
    committing, and always commits to a dedicated candidate branch rather than
    main. It never pushes or merges by itself.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=check,
        )

    def _validate_paths(self, paths: list[str]) -> None:
        for path in paths:
            normalize_selfdev_path(self.root, path)

    def _tracked_tree_clean(self) -> bool:
        unstaged = self._git("diff", "--quiet", check=False).returncode == 0
        staged = self._git("diff", "--cached", "--quiet", check=False).returncode == 0
        return unstaged and staged

    def next_builtin_improvement(self) -> dict:
        candidates = [
            {
                "title": "Add runtime health snapshot helper",
                "files": {
                    "genesis/health.py": (
                        "from __future__ import annotations\n\n"
                        "from dataclasses import dataclass, asdict\n"
                        "from datetime import datetime, timezone\n\n"
                        "@dataclass(frozen=True)\n"
                        "class HealthSnapshot:\n"
                        "    status: str\n"
                        "    created_at: str\n"
                        "    details: dict\n\n"
                        "def build_health_snapshot(**details) -> dict:\n"
                        "    snap = HealthSnapshot(\n"
                        "        status='ok',\n"
                        "        created_at=datetime.now(timezone.utc).isoformat(),\n"
                        "        details=details,\n"
                        "    )\n"
                        "    return asdict(snap)\n"
                    ),
                },
            },
            {
                "title": "Add bounded cycle budget helper",
                "files": {
                    "genesis/budget.py": (
                        "from __future__ import annotations\n\n"
                        "from dataclasses import dataclass\n\n"
                        "@dataclass(frozen=True)\n"
                        "class CycleBudget:\n"
                        "    max_actions: int = 8\n"
                        "    max_provider_calls: int = 4\n"
                        "    max_candidate_files: int = 6\n"
                    ),
                },
            },
        ]
        for proposal in candidates:
            path = next(iter(proposal["files"]))
            if not (self.root / path).exists():
                return proposal
        return {"title": "Record self-development idle state", "files": {}}

    def execute(self, proposal: dict) -> SelfDevResult:
        files = dict(proposal.get("files", {}))
        if not files:
            return SelfDevResult("", "", False, False, (), None, "proposal has no files")
        normalized_files: dict[str, str] = {}
        for raw_path, content in files.items():
            normalized = normalize_selfdev_path(self.root, str(raw_path))
            normalized_files[normalized] = str(content)
        if not self._tracked_tree_clean():
            return SelfDevResult("", "", False, False, (), None, "tracked tree is not clean")
        digest = hashlib.sha256(json.dumps(normalized_files, sort_keys=True).encode("utf-8")).hexdigest()[:12]
        branch = f"genesis/candidate-{digest}"
        candidate_id = digest
        self._git("checkout", "-B", branch)
        changed: list[str] = []
        try:
            for relative, content in normalized_files.items():
                normalized = normalize_selfdev_path(self.root, relative)
                path = self.root / normalized
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                changed.append(normalized)
            tests = subprocess.run(
                [os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"],
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
            if tests.returncode != 0:
                self._git("reset", "--hard", "HEAD", check=False)
                return SelfDevResult(branch, candidate_id, False, False, tuple(changed), None, "tests failed")
            self._git("add", "--", *changed)
            staged = self._git("diff", "--cached", "--name-only").stdout.splitlines()
            for path in staged:
                normalize_selfdev_path(self.root, path)
            if not staged:
                return SelfDevResult(branch, candidate_id, True, False, tuple(changed), None, "candidate produced no staged changes")
            title = str(proposal.get("title", "Genesis bounded candidate"))[:160]
            self._git("commit", "-m", title)
            sha = self._git("rev-parse", "HEAD").stdout.strip()
            return SelfDevResult(branch, candidate_id, True, True, tuple(staged), sha, "candidate committed")
        finally:
            pass

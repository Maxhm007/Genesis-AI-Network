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
                    "tests/test_health.py": (
                        "from genesis.health import build_health_snapshot\n\n"
                        "def test_health_snapshot():\n"
                        "    result = build_health_snapshot(node='test')\n"
                        "    assert result['status'] == 'ok'\n"
                        "    assert result['details']['node'] == 'test'\n"
                        "    assert result['created_at']\n"
                    ),
                },
            },
            {
                "title": "Add bounded cycle budget utility",
                "files": {
                    "genesis/budget.py": (
                        "from __future__ import annotations\n\n"
                        "from dataclasses import dataclass\n\n"
                        "@dataclass(frozen=True)\n"
                        "class CycleBudget:\n"
                        "    max_research_items: int = 5\n"
                        "    max_model_candidates: int = 10\n"
                        "    max_team_tasks: int = 8\n\n"
                        "    def validate(self) -> None:\n"
                        "        for value in (self.max_research_items, self.max_model_candidates, self.max_team_tasks):\n"
                        "            if value < 0 or value > 100:\n"
                        "                raise ValueError('cycle budget out of bounds')\n"
                    ),
                    "tests/test_budget.py": (
                        "import pytest\n"
                        "from genesis.budget import CycleBudget\n\n"
                        "def test_default_budget_valid():\n"
                        "    CycleBudget().validate()\n\n"
                        "def test_budget_rejects_unbounded_values():\n"
                        "    with pytest.raises(ValueError):\n"
                        "        CycleBudget(max_research_items=1000).validate()\n"
                    ),
                },
            },
        ]

        for candidate in candidates:
            # The first file is the production capability marker; supporting
            # tests are installed with the candidate but do not determine whether
            # that capability already exists.
            primary_path = next(iter(candidate["files"]))
            if not (self.root / primary_path).exists():
                return candidate
        return {
            "title": "Record self-development idle state",
            "files": {
                "docs/SELFDEV_STATUS.md": (
                    "# Self-development status\n\n"
                    "All built-in bootstrap improvements have already been applied.\n"
                    "Further code generation requires a validated intelligence provider or a newly approved improvement catalog entry.\n"
                )
            },
        }

    def execute(self, proposal: dict | None = None) -> SelfDevResult:
        proposal = proposal or self.next_builtin_improvement()
        raw_files = dict(proposal.get("files", {}))
        if not raw_files:
            raise RuntimeError("proposal contains no files")

        files: dict[str, object] = {}
        for relative, content in raw_files.items():
            normalized = normalize_selfdev_path(self.root, str(relative))
            if normalized in files:
                raise RuntimeError(f"duplicate self-development path: {normalized}")
            files[normalized] = content
        paths = list(files)
        self._validate_paths(paths)

        current_branch = self._git("branch", "--show-current").stdout.strip()
        if current_branch != "main":
            raise RuntimeError(f"self-development must start from main, got {current_branch or 'detached'}")
        if not self._tracked_tree_clean():
            raise RuntimeError("tracked working tree must be clean before self-development")

        base_sha = self._git("rev-parse", "HEAD").stdout.strip()
        safe_proposal = dict(proposal)
        safe_proposal["files"] = files
        payload = json.dumps(safe_proposal, sort_keys=True, separators=(",", ":"))
        candidate_seed = f"{base_sha}|{payload}"
        candidate_id = hashlib.sha256(candidate_seed.encode("utf-8")).hexdigest()[:12]
        branch = f"genesis/candidate-{candidate_id}"

        self._git("checkout", "-b", branch)
        try:
            for relative, content in files.items():
                # Revalidate immediately before the write to catch symlink/path
                # changes that occurred after proposal normalization.
                normalized = normalize_selfdev_path(self.root, relative)
                path = self.root / normalized
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(content), encoding="utf-8")

            test = subprocess.run(
                [os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"],
                cwd=self.root,
                text=True,
                capture_output=True,
            )
            if test.returncode != 0:
                self._git("reset", "--hard", "HEAD")
                return SelfDevResult(
                    branch=branch,
                    candidate_id=candidate_id,
                    tests_passed=False,
                    committed=False,
                    changed_files=tuple(paths),
                    commit_sha=None,
                    message=(test.stdout + "\n" + test.stderr)[-4000:],
                )

            self._git("add", "--", *paths)
            staged = self._git("diff", "--cached", "--name-only").stdout.splitlines()
            self._validate_paths(staged)
            if not staged:
                return SelfDevResult(branch, candidate_id, True, False, tuple(), None, "no changes")

            message = f"Genesis self-development candidate: {proposal.get('title','bounded improvement')}"
            self._git("commit", "-m", message)
            commit_sha = self._git("rev-parse", "HEAD").stdout.strip()
            return SelfDevResult(
                branch=branch,
                candidate_id=candidate_id,
                tests_passed=True,
                committed=True,
                changed_files=tuple(staged),
                commit_sha=commit_sha,
                message=message,
            )
        except Exception:
            self._git("reset", "--hard", "HEAD", check=False)
            raise

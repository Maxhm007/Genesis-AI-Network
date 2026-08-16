from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROTECTED_PATHS = {
    "GENESIS_CONSTITUTION.md",
    "GENESIS_BLOCK.json",
}

ALLOWED_PREFIXES = (
    "genesis/",
    "tests/",
    "docs/",
    "config/",
)


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
            normalized = path.replace("\\", "/").lstrip("./")
            if normalized in PROTECTED_PATHS:
                raise RuntimeError(f"protected path cannot be changed: {normalized}")
            if normalized.startswith(".github/"):
                raise RuntimeError("self-development may not modify GitHub workflow permissions")
            if not normalized.startswith(ALLOWED_PREFIXES):
                raise RuntimeError(f"path outside self-development sandbox: {normalized}")

    def next_builtin_improvement(self) -> dict:
        """Return the next small deterministic improvement candidate.

        This bootstrap catalog gives Genesis a real self-development path before
        a stronger model provider is available. Each item is intentionally small
        and auditable.
        """
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
            if not all((self.root / p).exists() for p in candidate["files"]):
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
        files = dict(proposal.get("files", {}))
        if not files:
            raise RuntimeError("proposal contains no files")
        paths = list(files)
        self._validate_paths(paths)

        payload = json.dumps(proposal, sort_keys=True, separators=(",", ":"))
        candidate_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        branch = f"genesis/candidate-{candidate_id}"

        current_branch = self._git("branch", "--show-current").stdout.strip()
        if current_branch != "main":
            raise RuntimeError(f"self-development must start from main, got {current_branch or 'detached'}")
        if self._git("status", "--porcelain").stdout.strip():
            raise RuntimeError("working tree must be clean before self-development")

        self._git("checkout", "-b", branch)
        try:
            for relative, content in files.items():
                path = self.root / relative
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

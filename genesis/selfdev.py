from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .autonomy_guard import AutonomyGuard
from .autonomy_proof import AutonomyProofLedger


PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}
ALLOWED_PREFIXES = ("genesis/", "tests/", "docs/", "config/", "desktop/", "mobile/", ".github/")


def normalize_selfdev_path(root: Path, path: str, *, allow_privileged: bool = False) -> str:
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
    if normalized.startswith(".github/") and not allow_privileged:
        raise RuntimeError("workflow changes require the privileged autonomy lane")
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
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.autonomy_guard = AutonomyGuard(self.root)
        self.autonomy_proof = AutonomyProofLedger(self.root)

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=check)

    def _validate_paths(self, paths: list[str], *, allow_privileged: bool = False) -> None:
        for path in paths:
            normalize_selfdev_path(self.root, path, allow_privileged=allow_privileged)

    def _tracked_tree_clean(self) -> bool:
        return self._git("diff", "--quiet", check=False).returncode == 0 and self._git("diff", "--cached", "--quiet", check=False).returncode == 0

    def _cleanup_new_paths(self, existed_before: dict[str, bool], *, allow_privileged: bool = False) -> None:
        for relative, existed in existed_before.items():
            if existed:
                continue
            normalized = normalize_selfdev_path(self.root, relative, allow_privileged=allow_privileged)
            target = self.root / normalized
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                shutil.rmtree(target)

    def _candidate_test_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.root)
        return env

    def next_builtin_improvement(self) -> dict:
        candidates = [
            {
                "title": "Add runtime health snapshot helper",
                "provenance": {"initiator": "genesis.selfdev", "discovery": "genesis.selfdev", "designer": "genesis.selfdev"},
                "files": {
                    "genesis/health.py": "from __future__ import annotations\n\nfrom dataclasses import dataclass, asdict\nfrom datetime import datetime, timezone\n\n@dataclass(frozen=True)\nclass HealthSnapshot:\n    status: str\n    created_at: str\n    details: dict\n\ndef build_health_snapshot(**details) -> dict:\n    snap = HealthSnapshot(status='ok', created_at=datetime.now(timezone.utc).isoformat(), details=details)\n    return asdict(snap)\n",
                    "tests/test_health.py": "from genesis.health import build_health_snapshot\n\ndef test_health_snapshot():\n    result = build_health_snapshot(node='test')\n    assert result['status'] == 'ok'\n    assert result['details']['node'] == 'test'\n    assert result['created_at']\n",
                },
            },
            {
                "title": "Add bounded cycle budget utility",
                "provenance": {"initiator": "genesis.selfdev", "discovery": "genesis.selfdev", "designer": "genesis.selfdev"},
                "files": {
                    "genesis/budget.py": "from __future__ import annotations\n\nfrom dataclasses import dataclass\n\n@dataclass(frozen=True)\nclass CycleBudget:\n    max_research_items: int = 5\n    max_model_candidates: int = 10\n    max_team_tasks: int = 8\n\n    def validate(self) -> None:\n        for value in (self.max_research_items, self.max_model_candidates, self.max_team_tasks):\n            if value < 0 or value > 100:\n                raise ValueError('cycle budget out of bounds')\n",
                    "tests/test_budget.py": "import pytest\nfrom genesis.budget import CycleBudget\n\ndef test_default_budget_valid():\n    CycleBudget().validate()\n\ndef test_budget_rejects_unbounded_values():\n    with pytest.raises(ValueError):\n        CycleBudget(max_research_items=1000).validate()\n",
                },
            },
        ]
        for candidate in candidates:
            if not (self.root / next(iter(candidate["files"]))).exists():
                return candidate
        return {
            "title": "Record self-development idle state",
            "provenance": {"initiator": "genesis.selfdev", "discovery": "genesis.selfdev", "designer": "genesis.selfdev"},
            "files": {"docs/SELFDEV_STATUS.md": "# Self-development status\n\nAll built-in bootstrap improvements have already been applied.\nFurther code generation requires a validated intelligence provider or a newly approved improvement catalog entry.\n"},
        }

    def execute(self, proposal: dict | None = None) -> SelfDevResult:
        proposal_supplied = proposal is not None
        proposal = proposal or self.next_builtin_improvement()
        provenance = dict(proposal.get("provenance", {}))
        actor = str(provenance.get("initiator") or ("external" if proposal_supplied else "genesis.selfdev"))
        raw_files = dict(proposal.get("files", {}))
        if not raw_files:
            raise RuntimeError("proposal contains no files")

        raw_paths = [str(relative).replace("\\", "/") for relative in raw_files]
        privileged = self.autonomy_guard.proposal_requires_privileged_lane(raw_paths)
        files: dict[str, object] = {}
        for relative, content in raw_files.items():
            normalized = normalize_selfdev_path(self.root, str(relative), allow_privileged=privileged)
            if normalized in files:
                raise RuntimeError(f"duplicate self-development path: {normalized}")
            files[normalized] = content
        paths = list(files)
        self._validate_paths(paths, allow_privileged=privileged)
        current_branch = self._git("branch", "--show-current").stdout.strip()
        if current_branch != "main":
            raise RuntimeError(f"self-development must start from main, got {current_branch or 'detached'}")
        if not self._tracked_tree_clean():
            raise RuntimeError("tracked working tree must be clean before self-development")

        existed_before = {relative: (self.root / relative).exists() for relative in paths}
        base_sha = self._git("rev-parse", "HEAD").stdout.strip()
        safe_proposal = dict(proposal)
        safe_proposal["files"] = files
        payload = json.dumps(safe_proposal, sort_keys=True, separators=(",", ":"))
        candidate_id = hashlib.sha256(f"{base_sha}|{payload}".encode("utf-8")).hexdigest()[:12]
        branch_prefix = "genesis/privileged-candidate-" if privileged else "genesis/candidate-"
        branch = f"{branch_prefix}{candidate_id}"
        self.autonomy_proof.record(cycle_id=candidate_id, stage="discovery", actor=actor, outcome="started", details={"title": proposal.get("title"), "files": paths, "privileged": privileged})
        self.autonomy_proof.record(cycle_id=candidate_id, stage="design", actor=str(provenance.get("designer") or actor), outcome="ready", details={"base_sha": base_sha})
        self._git("checkout", "-b", branch)
        try:
            for relative, content in files.items():
                normalized = normalize_selfdev_path(self.root, relative, allow_privileged=privileged)
                path = self.root / normalized
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(content), encoding="utf-8")

            diff_text = self._git("diff", "--", *paths).stdout
            decision = self.autonomy_guard.analyze(paths, diff_text)
            if not decision.autonomous_allowed:
                self.autonomy_proof.record(cycle_id=candidate_id, stage="cycle_complete", actor=actor, outcome="owner_escalation", details=decision.as_dict())
                self._git("reset", "--hard", "HEAD")
                self._cleanup_new_paths(existed_before, allow_privileged=privileged)
                raise RuntimeError("owner escalation required for high-risk self-development: " + "; ".join(decision.reasons))

            test = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"], cwd=self.root, text=True, capture_output=True, env=self._candidate_test_env())
            self.autonomy_proof.record(cycle_id=candidate_id, stage="test", actor="genesis.selfdev", outcome="success" if test.returncode == 0 else "failed", details={"returncode": test.returncode})
            if test.returncode != 0:
                self.autonomy_proof.record(cycle_id=candidate_id, stage="cycle_complete", actor=actor, outcome="failed", details={"reason": "tests_failed"})
                self._git("reset", "--hard", "HEAD")
                self._cleanup_new_paths(existed_before, allow_privileged=privileged)
                return SelfDevResult(branch, candidate_id, False, False, tuple(paths), None, (test.stdout + "\n" + test.stderr)[-4000:])

            self._git("add", "--", *paths)
            staged = self._git("diff", "--cached", "--name-only").stdout.splitlines()
            self._validate_paths(staged, allow_privileged=privileged)
            if not staged:
                self.autonomy_proof.record(cycle_id=candidate_id, stage="cycle_complete", actor=actor, outcome="failed", details={"reason": "no_changes"})
                return SelfDevResult(branch, candidate_id, True, False, tuple(), None, "no changes")
            message = f"Genesis self-development candidate: {proposal.get('title','bounded improvement')}"
            self._git("commit", "-m", message)
            commit_sha = self._git("rev-parse", "HEAD").stdout.strip()
            self.autonomy_proof.record(cycle_id=candidate_id, stage="candidate_created", actor=actor, outcome="success", details={"branch": branch, "commit_sha": commit_sha})
            self.autonomy_proof.record(cycle_id=candidate_id, stage="cycle_complete", actor=actor, outcome="success", details={"candidate_created": True, "validation_pending": True})
            return SelfDevResult(branch, candidate_id, True, True, tuple(staged), commit_sha, message)
        except Exception:
            self._git("reset", "--hard", "HEAD", check=False)
            self._cleanup_new_paths(existed_before, allow_privileged=privileged)
            raise

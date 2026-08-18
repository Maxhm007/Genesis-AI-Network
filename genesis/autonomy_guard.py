from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import subprocess


IMMUTABLE_PATHS = {
    "GENESIS_CONSTITUTION.md",
    "GENESIS_BLOCK.json",
}

PRIVILEGED_PREFIXES = (
    ".github/",
    "genesis/security.py",
    "genesis/autonomy_guard.py",
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "config/gden_peer_keys.json",
)

OWNER_ESCALATION_PATHS = {
    ".github/workflows/candidate-pr-gate.yml",
    ".github/workflows/independent-validator-gate.yml",
    ".github/workflows/secret-guard.yml",
    "genesis/autonomy_guard.py",
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
}

RISKY_DIFF_HINTS = (
    "id-token: write",
    "contents: write",
    "actions: write",
    "pull-requests: write",
    "issues: write",
    "packages: write",
    "deployments: write",
    "security-events: write",
    "--force",
    "reset --hard",
    "rm -rf",
)


@dataclass(frozen=True)
class AutonomyDecision:
    level: str
    risk_score: int
    autonomous_allowed: bool
    owner_escalation_required: bool
    changed_files: tuple[str, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


class AutonomyGuard:
    """Risk-gate Genesis self-development without disabling autonomous evolution.

    Level 0 paths remain immutable. Ordinary code evolves through normal candidate
    validation. Privileged workflow/security changes may evolve through the
    privileged-candidate lane when risk remains below the owner-escalation
    threshold. Changes to the guard itself, root validation gates, or other
    high-impact controls always require owner escalation.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    @staticmethod
    def is_privileged_path(path: str) -> bool:
        return any(path == prefix or path.startswith(prefix) for prefix in PRIVILEGED_PREFIXES)

    @classmethod
    def proposal_requires_privileged_lane(cls, paths: list[str] | tuple[str, ...]) -> bool:
        return any(cls.is_privileged_path(str(path)) for path in paths)

    def analyze(self, changed_files: list[str] | tuple[str, ...], diff_text: str = "") -> AutonomyDecision:
        files = tuple(sorted({str(path).replace("\\", "/") for path in changed_files if str(path).strip()}))
        reasons: list[str] = []
        score = 0

        immutable = sorted(set(files) & IMMUTABLE_PATHS)
        if immutable:
            reasons.append("immutable Genesis root changed: " + ", ".join(immutable))
            return AutonomyDecision("immutable", 100, False, True, files, tuple(reasons))

        privileged = [path for path in files if self.is_privileged_path(path)]
        if privileged:
            score += 25
            reasons.append("privileged workflow/security surface changed")

        escalation = sorted(set(files) & OWNER_ESCALATION_PATHS)
        if escalation:
            score += 45
            reasons.append("autonomy/validation root changed: " + ", ".join(escalation))

        lowered = diff_text.lower()
        for hint in RISKY_DIFF_HINTS:
            if hint in lowered:
                score += 10
                reasons.append(f"elevated permission/destructive hint detected: {hint}")

        if re.search(r"permissions:\s*\n(?:\s+\w[\w-]*:\s*write\s*\n?){2,}", diff_text, re.IGNORECASE):
            score += 15
            reasons.append("multiple GitHub write permissions requested")

        score = min(score, 100)
        if score >= 60:
            return AutonomyDecision("high_risk", score, False, True, files, tuple(reasons or ["high-risk change"]))
        if privileged:
            return AutonomyDecision("privileged", score, True, False, files, tuple(reasons))
        return AutonomyDecision("normal", score, True, False, files, tuple(reasons or ["ordinary bounded self-development"]))

    def analyze_git_candidate(self, base_ref: str = "origin/main") -> AutonomyDecision:
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        diff = subprocess.run(
            ["git", "diff", "--unified=0", f"{base_ref}...HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return self.analyze(changed, diff)

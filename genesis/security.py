from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .autonomy_guard import AutonomyGuard


@dataclass(frozen=True)
class SecurityFinding:
    finding_id: str
    severity: str
    title: str
    evidence: str
    remediation: str


@dataclass(frozen=True)
class SecurityReport:
    status: str
    findings: tuple[SecurityFinding, ...]
    checks: dict[str, bool]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "findings": [asdict(item) for item in self.findings],
            "checks": self.checks,
        }


class SecurityModule:
    """Bounded security control plane for Genesis.

    Security observes and reviews. It never silently modifies code or approves
    its own remediation. Candidate changes still require tests and independent
    validation before promotion. Privileged workflow changes are allowed only
    through the safeguarded privileged-candidate lane.
    """

    SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")
    SENSITIVE_NAMES = {".env", "credentials.json", "secrets.json"}
    PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}
    MAX_CANDIDATE_FILES = 6
    MAX_CANDIDATE_BYTES = 80_000

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, text=True, capture_output=True, check=False
        )

    def _tracked_files(self) -> list[str]:
        proc = self._git("ls-files")
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def inspect(self) -> SecurityReport:
        tracked = self._tracked_files()
        findings: list[SecurityFinding] = []

        exposed = [
            path for path in tracked
            if Path(path).name.lower() in self.SENSITIVE_NAMES
            or Path(path).suffix.lower() in self.SENSITIVE_SUFFIXES
        ]
        if exposed:
            findings.append(SecurityFinding(
                "tracked-sensitive-file", "high",
                "Potential sensitive file is tracked by Git",
                ", ".join(sorted(exposed)[:20]),
                "Remove sensitive material, rotate affected credentials, and review Git history.",
            ))

        protected_present = all((self.root / name).is_file() for name in self.PROTECTED_PATHS)
        if not protected_present:
            findings.append(SecurityFinding(
                "protected-identity-missing", "critical",
                "Protected Genesis identity file is missing",
                "GENESIS_CONSTITUTION.md and GENESIS_BLOCK.json must both exist.",
                "Stop autonomous operation and restore identity files from a verified release.",
            ))

        secret_guard_present = (self.root / "scripts" / "secret_guard.py").is_file()
        if not secret_guard_present:
            findings.append(SecurityFinding(
                "secret-guard-missing", "medium",
                "Permanent secret guard is unavailable",
                "scripts/secret_guard.py was not found.",
                "Restore the secret scanning guard and require it in CI.",
            ))

        checks = {
            "protected_identity_present": protected_present,
            "secret_guard_present": secret_guard_present,
            "no_tracked_sensitive_files": not exposed,
        }
        return SecurityReport("pass" if not findings else "findings", tuple(findings), checks)

    def review_candidate(self, base_ref: str = "main") -> SecurityReport:
        """Review the actual candidate diff before external validation."""
        findings: list[SecurityFinding] = []
        proc = self._git("diff", "--name-only", f"{base_ref}..HEAD")
        if proc.returncode != 0:
            return SecurityReport(
                "findings",
                (SecurityFinding(
                    "candidate-diff-unavailable", "high",
                    "Candidate security diff could not be resolved",
                    proc.stderr[-1000:],
                    "Do not promote until the candidate can be compared with its trusted base.",
                ),),
                {"candidate_diff_resolved": False},
            )
        changed = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        immutable = [p for p in changed if p in self.PROTECTED_PATHS]
        workflow_changes = [p for p in changed if p.startswith(".github/")]
        branch = self._git("branch", "--show-current").stdout.strip()
        privileged_lane = (
            os.environ.get("GENESIS_CANDIDATE_LANE", "").strip().lower() == "privileged"
            or os.environ.get("GITHUB_HEAD_REF", "").startswith("genesis/privileged-candidate-")
            or branch.startswith("genesis/privileged-candidate-")
        )

        if immutable:
            findings.append(SecurityFinding(
                "candidate-forbidden-path", "critical",
                "Candidate modifies an immutable Genesis identity boundary",
                ", ".join(immutable),
                "Reject the candidate; immutable Genesis identity requires explicit owner governance.",
            ))

        if workflow_changes and not privileged_lane:
            findings.append(SecurityFinding(
                "candidate-workflow-outside-privileged-lane", "critical",
                "Workflow/security change is outside the privileged autonomy lane",
                ", ".join(workflow_changes),
                "Recreate the change on a genesis/privileged-candidate-* branch for risk-gated validation.",
            ))
        elif workflow_changes:
            decision = AutonomyGuard(self.root).analyze_git_candidate(base_ref)
            if not decision.autonomous_allowed:
                findings.append(SecurityFinding(
                    "candidate-privileged-risk-escalation", "critical",
                    "Privileged candidate exceeds autonomous risk threshold",
                    "; ".join(decision.reasons),
                    "Pause autonomous promotion and escalate to the owner with the exact risk evidence.",
                ))

        sensitive = [
            p for p in changed
            if Path(p).name.lower() in self.SENSITIVE_NAMES
            or Path(p).suffix.lower() in self.SENSITIVE_SUFFIXES
        ]
        if sensitive:
            findings.append(SecurityFinding(
                "candidate-sensitive-file", "critical",
                "Candidate introduces or modifies sensitive file types",
                ", ".join(sensitive),
                "Reject the candidate and keep secrets in local or secret-managed state only.",
            ))
        if len(changed) > self.MAX_CANDIDATE_FILES:
            findings.append(SecurityFinding(
                "candidate-too-wide", "high",
                "Candidate exceeds bounded file-change limit",
                f"changed_files={len(changed)}",
                "Split the work into smaller independently reviewable candidates.",
            ))
        stat = self._git("diff", "--numstat", f"{base_ref}..HEAD")
        approx_bytes = len((stat.stdout + proc.stdout).encode("utf-8"))
        if approx_bytes > self.MAX_CANDIDATE_BYTES:
            findings.append(SecurityFinding(
                "candidate-review-size", "medium",
                "Candidate review metadata is unexpectedly large",
                f"review_bytes={approx_bytes}",
                "Reduce candidate scope before promotion.",
            ))
        checks = {
            "candidate_diff_resolved": True,
            "protected_paths_unchanged": not immutable,
            "workflow_change_safeguarded": not workflow_changes or privileged_lane,
            "no_sensitive_files_changed": not sensitive,
            "bounded_file_count": len(changed) <= self.MAX_CANDIDATE_FILES,
        }
        return SecurityReport("pass" if not findings else "findings", tuple(findings), checks)

    def write_report(self, path: Path, *, candidate: bool = False, base_ref: str = "main") -> dict:
        report = (self.review_candidate(base_ref) if candidate else self.inspect()).as_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

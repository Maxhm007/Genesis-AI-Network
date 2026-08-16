from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


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

    This module performs deterministic repository checks and records findings.
    It does not silently modify code, rotate credentials, weaken validation, or
    treat model-generated security claims as verified vulnerabilities.
    """

    SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")
    SENSITIVE_NAMES = {".env", "credentials.json", "secrets.json"}

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _tracked_files(self) -> list[str]:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
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
                finding_id="tracked-sensitive-file",
                severity="high",
                title="Potential sensitive file is tracked by Git",
                evidence=", ".join(sorted(exposed)[:20]),
                remediation="Remove the sensitive material from Git, rotate affected credentials, and review repository history.",
            ))

        protected_present = all((self.root / name).is_file() for name in (
            "GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"
        ))
        if not protected_present:
            findings.append(SecurityFinding(
                finding_id="protected-identity-missing",
                severity="critical",
                title="Protected Genesis identity file is missing",
                evidence="GENESIS_CONSTITUTION.md and GENESIS_BLOCK.json must both exist.",
                remediation="Stop autonomous operation and restore identity files from a verified release.",
            ))

        secret_guard_present = (self.root / "scripts" / "secret_guard.py").is_file()
        if not secret_guard_present:
            findings.append(SecurityFinding(
                finding_id="secret-guard-missing",
                severity="medium",
                title="Permanent secret guard is unavailable",
                evidence="scripts/secret_guard.py was not found.",
                remediation="Restore the secret scanning guard and require it in CI.",
            ))

        checks = {
            "protected_identity_present": protected_present,
            "secret_guard_present": secret_guard_present,
            "no_tracked_sensitive_files": not exposed,
        }
        status = "pass" if not findings else "findings"
        return SecurityReport(status, tuple(findings), checks)

    def write_report(self, path: Path) -> dict:
        report = self.inspect().as_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report

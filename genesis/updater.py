from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}
PROTECTED_PREFIXES = (".github/",)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class UpdateDecision:
    candidate_sha: str
    status: str
    eligible: bool
    reasons: tuple[str, ...]
    changed_files: tuple[str, ...]
    checked_at: str

    def as_dict(self) -> dict:
        return asdict(self)


class UpdaterModule:
    """Fail-closed update coordinator for Genesis.

    The module never grants itself release authority. It decides whether a
    candidate is eligible to enter the existing protected promotion path.
    Security approval and independent validator quorum remain mandatory.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.runtime / "updater_audit.jsonl"

    @staticmethod
    def _protected(path: str) -> bool:
        normalized = path.replace("\\", "/").lstrip("./")
        return normalized in PROTECTED_PATHS or normalized.startswith(PROTECTED_PREFIXES)

    def evaluate(
        self,
        candidate_sha: str,
        changed_files: list[str] | tuple[str, ...],
        *,
        tests_passed: bool,
        security_passed: bool,
        validator_approvals: int,
        required_validator_approvals: int = 2,
    ) -> UpdateDecision:
        files = tuple(str(p).replace("\\", "/").lstrip("./") for p in changed_files)
        reasons: list[str] = []
        if not candidate_sha.strip():
            reasons.append("candidate identity missing")
        if not files:
            reasons.append("candidate contains no changed files")
        protected = [path for path in files if self._protected(path)]
        if protected:
            reasons.append("protected boundary changed: " + ", ".join(protected))
        if not tests_passed:
            reasons.append("tests have not passed")
        if not security_passed:
            reasons.append("Security review has not passed")
        if required_validator_approvals < 1:
            reasons.append("invalid validator quorum requirement")
        elif validator_approvals < required_validator_approvals:
            reasons.append(
                f"independent validator quorum missing: {validator_approvals}/{required_validator_approvals}"
            )

        eligible = not reasons
        decision = UpdateDecision(
            candidate_sha=candidate_sha.strip(),
            status="eligible_for_protected_promotion" if eligible else "blocked",
            eligible=eligible,
            reasons=tuple(reasons),
            changed_files=files,
            checked_at=utc_now(),
        )
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.as_dict(), sort_keys=True) + "\n")
        return decision

    def status(self) -> dict:
        entries = 0
        last = None
        if self.audit_path.exists():
            for line in self.audit_path.read_text(encoding="utf-8").splitlines():
                try:
                    last = json.loads(line)
                    entries += 1
                except Exception:
                    continue
        return {
            "module": "genesis.updater",
            "status": "active",
            "automatic_unvalidated_update": False,
            "release_authority": False,
            "protected_identity_writable": False,
            "audit_entries": entries,
            "last_decision": last,
        }

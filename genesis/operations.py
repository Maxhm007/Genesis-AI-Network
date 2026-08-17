from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OperationalIssue:
    issue_key: str
    title: str
    severity: str
    module_id: str
    status: str
    evidence: str
    remediation: str
    owner_action_required: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class GenesisOperations:
    """Detect, persist and queue operational issues without bypassing validation.

    The ledger is an audit/reporting surface. Repair authority remains with the
    existing bounded engineering loop, Security review and independent validators.
    """

    VALID_SEVERITY = {"info", "low", "medium", "high", "critical"}

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.ledger_path = self.runtime / "operations_issues.jsonl"

    @staticmethod
    def _stable_key(title: str, evidence: str) -> str:
        raw = f"{title.strip()}\n{evidence.strip()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]

    def detect(self, scorecard: dict) -> list[OperationalIssue]:
        issues: list[OperationalIssue] = []
        ai = scorecard.get("ai_capability_score", {})
        eff = scorecard.get("efficiency_score", {})
        mission = scorecard.get("immortality_research_progress_score", {})

        if int(ai.get("score", 0)) < 50:
            issues.append(OperationalIssue(
                self._stable_key("AI capability below target", str(ai)),
                "AI capability below target",
                "high",
                "genesis.ai_score",
                "open",
                f"AI Capability Score={ai.get('score', 'Unmeasured')}/{ai.get('max_score', 100)}",
                "Increase real benchmark coverage and measured capability; do not award architecture-only credit.",
            ))

        samples = int(eff.get("samples", 0) or 0)
        if samples < 3:
            issues.append(OperationalIssue(
                self._stable_key("Efficiency telemetry insufficient", f"samples={samples}"),
                "Efficiency telemetry insufficient",
                "medium",
                "genesis.coding",
                "open",
                f"Efficiency samples={samples}; score={eff.get('score', 0)}",
                "Capture qualifying completed-task measurements and feed validated telemetry to routing.",
            ))

        if not bool(mission.get("fresh_scan_24h", False)):
            issues.append(OperationalIssue(
                self._stable_key("Immortality research scan stale", str(mission.get('fresh_scan_24h'))),
                "Immortality research scan stale",
                "high",
                "genesis.ai_score",
                "open",
                "No fresh immortality-source scan in the last 24 hours.",
                "Run the configured public scientific source scan and preserve provenance.",
            ))

        security_path = self.runtime / "security_report.json"
        if security_path.exists():
            try:
                report = json.loads(security_path.read_text(encoding="utf-8"))
                for finding in report.get("findings", []):
                    sev = str(finding.get("severity", "medium")).lower()
                    if sev not in self.VALID_SEVERITY:
                        sev = "medium"
                    evidence = str(finding.get("evidence", finding.get("title", "security finding")))
                    title = f"Security: {finding.get('title', 'finding')}"
                    issues.append(OperationalIssue(
                        self._stable_key(title, evidence), title, sev, "genesis.security", "open", evidence,
                        str(finding.get("remediation", "Investigate and remediate through bounded candidate workflow.")),
                    ))
            except Exception:
                pass

        app_path = self.runtime / "application_status.json"
        if app_path.exists():
            try:
                report = json.loads(app_path.read_text(encoding="utf-8"))
                for item in report.get("issues", []):
                    title = str(item.get("title", "Application issue"))
                    evidence = str(item.get("evidence", item))
                    issues.append(OperationalIssue(
                        self._stable_key(title, evidence), title, str(item.get("severity", "medium")),
                        "genesis.application", "blocked" if item.get("owner_action_required") else "open",
                        evidence, str(item.get("remediation", "Repair through Application Module candidate workflow.")),
                        bool(item.get("owner_action_required", False)),
                    ))
            except Exception:
                pass

        return issues

    def persist_and_queue(self, issues: list[OperationalIssue]) -> dict:
        existing: dict[str, dict] = {}
        if self.ledger_path.exists():
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    existing[row["issue_key"]] = row
                except Exception:
                    continue

        now = utc_now()
        created_tasks: list[str] = []
        rows: list[dict] = []
        current_keys = {issue.issue_key for issue in issues}

        for key, old in existing.items():
            if key not in current_keys and old.get("status") in {"open", "blocked"}:
                old = dict(old)
                old["status"] = "resolved"
                old["resolved_at"] = now
                rows.append(old)

        for issue in issues:
            row = issue.as_dict()
            prior = existing.get(issue.issue_key, {})
            row["first_seen_at"] = prior.get("first_seen_at", now)
            row["last_seen_at"] = now
            if prior.get("status") == "resolved":
                row["reopened_at"] = now
            rows.append(row)

            if issue.owner_action_required:
                continue
            priority = {"info": 20, "low": 40, "medium": 70, "high": 90, "critical": 100}.get(issue.severity, 70)
            task, created = self.queue.create_unique(
                f"ops:{issue.issue_key}",
                f"Resolve detected Genesis issue: {issue.title}. {issue.remediation}",
                module_id=issue.module_id,
                priority=priority,
                payload={
                    "task_type": "operational_issue",
                    "issue_key": issue.issue_key,
                    "severity": issue.severity,
                    "evidence": issue.evidence,
                    "remediation": issue.remediation,
                    "source": "genesis_operations",
                },
            )
            if created:
                created_tasks.append(task.task_id)

        # Keep one latest row per issue key.
        compact = {}
        for row in rows:
            compact[row["issue_key"]] = row
        ordered = sorted(compact.values(), key=lambda r: (r.get("status") == "resolved", r.get("severity", ""), r.get("first_seen_at", "")))
        self.ledger_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in ordered), encoding="utf-8")
        return {"issues": ordered, "created_tasks": created_tasks, "updated_at": now}

    def report(self) -> dict:
        if not self.ledger_path.exists():
            return {"issues": [], "open": 0, "blocked": 0, "resolved": 0}
        rows = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return {
            "issues": rows,
            "open": sum(1 for r in rows if r.get("status") == "open"),
            "blocked": sum(1 for r in rows if r.get("status") == "blocked"),
            "resolved": sum(1 for r in rows if r.get("status") == "resolved"),
        }

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .modules.task_queue import GenesisTask, PersistentTaskQueue


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
    """Detect, remember and keep working operational issues until resolved."""

    VALID_SEVERITY = {"info", "low", "medium", "high", "critical"}
    ACTIVE_TASK_STATES = {"new", "assigned", "running", "blocked", "review"}
    EMBEDDED_HISTORY_LIMIT = 50
    OWNER_EXTERNAL_BENCHMARK_BLOCKER_PREFIX = "External owner authority required for real benchmark execution:"
    BENCHMARK_TERMINAL_STATES = {"complete", "cancelled"}

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = PersistentTaskQueue(self.runtime / "genesis_tasks.sqlite3")
        self.ledger_path = self.runtime / "operations_issues.jsonl"
        self.history_path = self.runtime / "operations_issue_history.jsonl"
        self._restore_embedded_history()

    @staticmethod
    def _stable_key(title: str, identity: str) -> str:
        raw = f"{title.strip()}\n{identity.strip()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]

    def _restore_embedded_history(self) -> None:
        if self.history_path.exists() or not self.ledger_path.exists():
            return
        events: list[dict] = []
        seen: set[str] = set()
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            for event in row.get("history_snapshot", []) if isinstance(row, dict) else []:
                if not isinstance(event, dict):
                    continue
                marker = json.dumps(event, sort_keys=True)
                if marker in seen:
                    continue
                seen.add(marker)
                events.append(event)
        if events:
            events.sort(key=lambda item: str(item.get("at", "")))
            self.history_path.write_text(
                "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
                encoding="utf-8",
            )

    def _append_history(self, event: str, issue_key: str, **payload) -> dict:
        row = {"at": utc_now(), "event": event, "issue_key": issue_key, **payload}
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def history(self, issue_key: str | None = None, limit: int = 500) -> list[dict]:
        if not self.history_path.exists():
            return []
        rows: list[dict] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if issue_key is None or row.get("issue_key") == issue_key:
                rows.append(row)
        return rows[-max(1, limit):]

    def _tasks_for_issue(self, issue_key: str):
        return [task for task in self.queue.list(limit=5000) if task.payload.get("issue_key") == issue_key]

    def _unresolved_benchmark_tasks(self, issue: OperationalIssue) -> list[GenesisTask]:
        if issue.title != "AI capability below target":
            return []
        return [
            task
            for task in self.queue.list(limit=5000)
            if task.module_id == "genesis.evaluation"
            and task.payload.get("task_type") == "frontier_benchmark_measurement"
            and task.state not in self.BENCHMARK_TERMINAL_STATES
        ]

    def _delegated_external_blocker(self, issue: OperationalIssue) -> GenesisTask | None:
        """Return an owner blocker only when every unresolved benchmark needs owner authority.

        A single paused benchmark must not freeze the entire AI-capability program.
        Non-owner evidence gaps and autonomous runner-integration work remain delegated
        Genesis work, so the operational issue stays open rather than falsely asking
        the owner to resolve the whole capability problem.
        """
        unresolved = self._unresolved_benchmark_tasks(issue)
        if not unresolved:
            return None
        owner_blockers = [
            task
            for task in unresolved
            if task.state == "paused"
            and str(task.state_reason or "").startswith(self.OWNER_EXTERNAL_BENCHMARK_BLOCKER_PREFIX)
        ]
        if len(owner_blockers) != len(unresolved):
            return None
        return max(owner_blockers, key=lambda task: task.updated_at)

    def _delegated_benchmark_work(self, issue: OperationalIssue) -> GenesisTask | None:
        unresolved = self._unresolved_benchmark_tasks(issue)
        if not unresolved:
            return None
        state_rank = {
            "running": 0,
            "assigned": 1,
            "new": 2,
            "review": 3,
            "blocked": 4,
            "failed": 5,
            "paused": 6,
            "quarantined": 7,
        }
        return min(
            unresolved,
            key=lambda task: (state_rank.get(task.state, 99), -int(task.priority), task.created_at),
        )

    def _ensure_issue_work(self, issue: OperationalIssue) -> tuple[str | None, int]:
        tasks = self._tasks_for_issue(issue.issue_key)
        active = [task for task in tasks if task.state in self.ACTIVE_TASK_STATES]
        if active:
            return None, len(tasks)
        generation = len(tasks) + 1
        priority = {"info": 20, "low": 40, "medium": 70, "high": 90, "critical": 100}.get(issue.severity, 70)
        task, created = self.queue.create_unique(
            f"ops:{issue.issue_key}:work:{generation}",
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
                "work_generation": generation,
                "gene_coordinator": "Gene 0",
            },
        )
        if not created:
            return None, generation
        self._append_history(
            "repair_task_created",
            issue.issue_key,
            task_id=task.task_id,
            work_generation=generation,
            module_id=issue.module_id,
            priority=priority,
        )
        return task.task_id, generation

    def detect(self, scorecard: dict) -> list[OperationalIssue]:
        issues: list[OperationalIssue] = []
        ai = scorecard.get("ai_capability_score", {})
        eff = scorecard.get("efficiency_score", {})
        mission = scorecard.get("immortality_research_progress_score", {})

        if int(ai.get("score", 0)) < 50:
            issues.append(OperationalIssue(
                self._stable_key("AI capability below target", "ai_capability_score_below_50"),
                "AI capability below target", "high", "genesis.ai_score", "open",
                f"AI Capability Score={ai.get('score', 'Unmeasured')}/{ai.get('max_score', 100)}",
                "Increase real benchmark coverage and measured capability; do not award architecture-only credit.",
            ))

        samples = int(eff.get("samples", 0) or 0)
        if samples < 3:
            issues.append(OperationalIssue(
                self._stable_key("Efficiency telemetry insufficient", "efficiency_samples_below_3"),
                "Efficiency telemetry insufficient", "medium", "genesis.coding", "open",
                f"Efficiency samples={samples}; score={eff.get('score', 0)}",
                "Capture qualifying completed-task measurements and feed validated telemetry to routing.",
            ))

        if not bool(mission.get("fresh_scan_24h", False)):
            issues.append(OperationalIssue(
                self._stable_key("Immortality research scan stale", "immortality_scan_not_fresh_24h"),
                "Immortality research scan stale", "high", "genesis.ai_score", "open",
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
            if key in current_keys:
                continue
            if old.get("status") in {"open", "blocked"}:
                resolved = dict(old)
                resolved["status"] = "resolved"
                resolved["resolved_at"] = now
                rows.append(resolved)
                self._append_history("resolved", key, title=old.get("title"), previous_status=old.get("status"))
            elif old.get("status") == "resolved":
                # Resolved issues are historical evidence, not transient output. Keep the
                # tombstone indefinitely so later hourly reports and dashboards cannot
                # forget a resolution simply because another collection cycle ran.
                rows.append(dict(old))

        for issue in issues:
            row = issue.as_dict()
            prior = existing.get(issue.issue_key, {})
            row["first_seen_at"] = prior.get("first_seen_at", now)
            row["last_seen_at"] = now
            blocker = self._delegated_external_blocker(issue)
            benchmark_work = None if blocker is not None else self._delegated_benchmark_work(issue)

            if prior.get("status") == "resolved":
                row["reopened_at"] = now
                self._append_history("reopened", issue.issue_key, title=issue.title, evidence=issue.evidence)
            elif not prior:
                self._append_history("detected", issue.issue_key, title=issue.title, severity=issue.severity, evidence=issue.evidence)
            elif blocker is None and prior.get("status") == "blocked" and prior.get("delegated_task_id"):
                self._append_history(
                    "delegated_blocker_cleared",
                    issue.issue_key,
                    title=issue.title,
                    delegated_task_id=prior.get("delegated_task_id"),
                )
            elif blocker is None and benchmark_work is None:
                self._append_history("observed_open", issue.issue_key, title=issue.title, evidence=issue.evidence)

            if blocker is not None:
                row["status"] = "blocked"
                row["owner_action_required"] = True
                row["delegated_task_id"] = blocker.task_id
                row["blocker_reason"] = blocker.state_reason
                row["work_generation"] = len(self._tasks_for_issue(issue.issue_key))
                self._append_history(
                    "delegated_external_blocker",
                    issue.issue_key,
                    title=issue.title,
                    delegated_task_id=blocker.task_id,
                    blocker_reason=blocker.state_reason,
                )
            elif benchmark_work is not None:
                row["status"] = "open"
                row["owner_action_required"] = False
                row["delegated_task_id"] = benchmark_work.task_id
                row["delegated_task_state"] = benchmark_work.state
                row["work_generation"] = len(self._tasks_for_issue(issue.issue_key))
                if prior.get("delegated_task_id") != benchmark_work.task_id or prior.get("status") == "blocked":
                    self._append_history(
                        "delegated_benchmark_work",
                        issue.issue_key,
                        title=issue.title,
                        delegated_task_id=benchmark_work.task_id,
                        delegated_task_state=benchmark_work.state,
                    )
            elif not issue.owner_action_required:
                task_id, generation = self._ensure_issue_work(issue)
                if task_id:
                    created_tasks.append(task_id)
                row["work_generation"] = generation
            rows.append(row)

        compact = {row["issue_key"]: row for row in rows}
        ordered = sorted(
            compact.values(),
            key=lambda r: (r.get("status") == "resolved", r.get("severity", ""), r.get("first_seen_at", "")),
        )
        for row in ordered:
            row["history_snapshot"] = self.history(row["issue_key"], limit=self.EMBEDDED_HISTORY_LIMIT)
        self.ledger_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in ordered),
            encoding="utf-8",
        )
        return {"issues": ordered, "created_tasks": created_tasks, "updated_at": now, "history_events": len(self.history())}

    def report(self) -> dict:
        if not self.ledger_path.exists():
            return {"issues": [], "open": 0, "blocked": 0, "resolved": 0, "history_events": len(self.history())}
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
            "history_events": len(self.history()),
        }

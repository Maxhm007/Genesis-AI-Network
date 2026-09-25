from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .autonomy_guard import AutonomyGuard


WORKFLOW_DIR = Path(".github/workflows")
PROTECTED_WORKFLOWS = {
    "genesis-workflow-governor.yml",
    "genesis-workflow-governor-validator.yml",
    "genesis-sequential-issue-controller.yml",
    "genesis-bounded-repair-worker.yml",
    "genesis-agentic-lab-recovery.yml",
    "github-issue-terminal-reconciler.yml",
    "genesis-action-failure-watcher.yml",
    "genesis-action-repair-worker.yml",
    "genesis-action-repair-validator.yml",
    "genesis-closed-issue-seal.yml",
    "secret-guard.yml",
    "candidate-pr-gate.yml",
    "independent-validator-gate.yml",
}
TEMPORARY_PATTERNS = (
    re.compile(r"(^|[-_])task\d+([-_]|$)", re.I),
    re.compile(r"(^|[-_])validate[-_]", re.I),
    re.compile(r"(^|[-_])test([-_.]|$)", re.I),
)
WRITE_PERMISSION_RE = re.compile(r"^\s{2,}([a-z-]+):\s*write\s*$", re.M)
WORKFLOW_REF_RE = re.compile(r"([A-Za-z0-9._-]+\.(?:yml|yaml))")


@dataclass(frozen=True)
class WorkflowInfo:
    path: str
    name: str
    crons: tuple[str, ...]
    has_schedule: bool
    has_dispatch: bool
    has_push: bool
    has_issues: bool
    has_workflow_run: bool
    concurrency_group: str
    write_permissions: tuple[str, ...]
    workflow_refs: tuple[str, ...]
    lines: int


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    workflow: str
    recommendation: str
    evidence: str
    auto_action: str | None = None


@dataclass(frozen=True)
class GovernanceReport:
    generated_at: int
    workflows: tuple[WorkflowInfo, ...]
    findings: tuple[Finding, ...]

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "workflow_count": len(self.workflows),
            "finding_count": len(self.findings),
            "workflows": [asdict(x) for x in self.workflows],
            "findings": [asdict(x) for x in self.findings],
        }


def _section_present(text: str, key: str) -> bool:
    return bool(re.search(rf"^\s{{2}}{re.escape(key)}\s*:", text, re.M))


def inspect_workflow(path: Path) -> WorkflowInfo:
    text = path.read_text(encoding="utf-8")
    name_match = re.search(r"^name:\s*(.+?)\s*$", text, re.M)
    group_match = re.search(r"^\s{2}group:\s*(.+?)\s*$", text, re.M)
    crons = tuple(m.group(1).strip() for m in re.finditer(r"cron:\s*['\"]?([^'\"\n]+)", text))
    refs = sorted({
        ref for ref in WORKFLOW_REF_RE.findall(text)
        if ref != path.name and (
            "workflow run " + ref in text
            or f"/actions/workflows/{ref}/" in text
            or f"actions/workflows/{ref}/" in text
        )
    })
    return WorkflowInfo(
        path=path.as_posix(),
        name=(name_match.group(1).strip() if name_match else path.stem),
        crons=crons,
        has_schedule=_section_present(text, "schedule"),
        has_dispatch=_section_present(text, "workflow_dispatch"),
        has_push=_section_present(text, "push"),
        has_issues=_section_present(text, "issues"),
        has_workflow_run=_section_present(text, "workflow_run"),
        concurrency_group=(group_match.group(1).strip() if group_match else ""),
        write_permissions=tuple(sorted(set(WRITE_PERMISSION_RE.findall(text)))),
        workflow_refs=tuple(refs),
        lines=len(text.splitlines()),
    )


def inventory(root: Path) -> tuple[WorkflowInfo, ...]:
    workflow_root = root / WORKFLOW_DIR
    rows = []
    for path in sorted(list(workflow_root.glob("*.yml")) + list(workflow_root.glob("*.yaml"))):
        rows.append(inspect_workflow(path))
    return tuple(rows)


def _reference_counts(root: Path, names: set[str]) -> dict[str, int]:
    counts = {name: 0 for name in names}
    ignored = {".git", "__pycache__", ".pytest_cache", "runtime"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".yml", ".yaml", ".md", ".json", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in names:
            if name in text and path.name != name:
                counts[name] += text.count(name)
    return counts


def _workflow_age_days(root: Path, relative: str) -> float | None:
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", relative],
        cwd=root, text=True, capture_output=True, check=False,
    )
    raw = proc.stdout.strip()
    if not raw.isdigit():
        return None
    return max(0.0, (time.time() - int(raw)) / 86400.0)


def analyze(root: Path) -> GovernanceReport:
    root = root.resolve()
    workflows = inventory(root)
    by_name = {Path(w.path).name: w for w in workflows}
    refs = _reference_counts(root, set(by_name))
    findings: list[Finding] = []

    groups: dict[str, list[WorkflowInfo]] = {}
    for w in workflows:
        if w.concurrency_group and w.has_schedule:
            groups.setdefault(w.concurrency_group, []).append(w)
    for group, members in sorted(groups.items()):
        if len(members) > 1:
            names = ", ".join(Path(x.path).name for x in members)
            for w in members:
                findings.append(Finding(
                    "duplicate_concurrency_group", "high", w.path,
                    "Merge overlapping schedulers or give genuinely independent lanes distinct ownership.",
                    f"scheduled workflows share concurrency group {group}: {names}",
                ))

    cron_map: dict[str, list[WorkflowInfo]] = {}
    for w in workflows:
        for cron in w.crons:
            cron_map.setdefault(cron, []).append(w)
    for cron, members in sorted(cron_map.items()):
        if len(members) >= 3:
            findings.append(Finding(
                "schedule_collision", "medium", members[0].path,
                "Stagger schedules unless the workflows intentionally form one coordinated boundary.",
                f"{len(members)} workflows use identical cron {cron}: " +
                ", ".join(Path(x.path).name for x in members),
            ))

    for w in workflows:
        filename = Path(w.path).name
        for ref in w.workflow_refs:
            if ref not in by_name:
                findings.append(Finding(
                    "dangling_workflow_reference", "high", w.path,
                    "Repair or remove the reference before the next dispatch.",
                    f"{filename} references missing workflow {ref}",
                ))

        lower_name = (w.name + " " + filename).lower()
        dispatched_by_other = refs.get(filename, 0) > 0
        looks_like_worker = any(token in lower_name for token in ("worker", "solver"))
        if (
            w.has_schedule and w.has_dispatch and dispatched_by_other and looks_like_worker
            and filename not in PROTECTED_WORKFLOWS
        ):
            findings.append(Finding(
                "scheduled_dispatch_worker", "medium", w.path,
                "Prefer controller-owned dispatch; remove the independent schedule if it duplicates controller routing.",
                f"{filename} is scheduled and also referenced {refs.get(filename, 0)} time(s)",
                "remove_schedule",
            ))

        age = _workflow_age_days(root, w.path)
        looks_temporary = any(p.search(filename) for p in TEMPORARY_PATTERNS)
        if (
            looks_temporary and filename not in PROTECTED_WORKFLOWS
            and refs.get(filename, 0) == 0 and age is not None and age >= 14
        ):
            findings.append(Finding(
                "stale_temporary_workflow", "low", w.path,
                "Delete this unreferenced temporary workflow after candidate validation.",
                f"unreferenced temporary/test workflow; last workflow-file commit age={age:.1f} days",
                "delete",
            ))

    required = {
        "genesis-workflow-governor.yml",
        "genesis-workflow-governor-validator.yml",
        "genesis-sequential-issue-controller.yml",
        "genesis-agentic-lab-recovery.yml",
        "github-issue-terminal-reconciler.yml",
    }
    for missing in sorted(required - set(by_name)):
        findings.append(Finding(
            "missing_core_workflow", "critical", str(WORKFLOW_DIR / missing),
            "Create or restore the missing core workflow through the privileged candidate lane.",
            f"required governance/issue-lifecycle workflow is absent: {missing}",
        ))

    return GovernanceReport(int(time.time()), workflows, tuple(findings))


def remove_schedule_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s{2}schedule:\s*$", line):
            start = i
            break
    if start is None:
        return text
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip():
            end += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= 2:
            break
        end += 1
    return "".join(lines[:start] + lines[end:])


def choose_autonomous_action(report: GovernanceReport) -> Finding | None:
    priority = {"delete": 0, "remove_schedule": 1}
    candidates = [
        f for f in report.findings
        if f.auto_action in priority and Path(f.workflow).name not in PROTECTED_WORKFLOWS
    ]
    candidates.sort(key=lambda f: (priority[f.auto_action or ""], f.workflow))
    return candidates[0] if candidates else None


def apply_candidate(root: Path, finding: Finding) -> tuple[str, tuple[str, ...]]:
    root = root.resolve()
    target = root / finding.workflow
    if Path(finding.workflow).name in PROTECTED_WORKFLOWS:
        raise RuntimeError(f"workflow governor refuses protected target: {finding.workflow}")
    if finding.auto_action == "delete":
        if not target.is_file():
            raise RuntimeError(f"delete target missing: {finding.workflow}")
        target.unlink()
    elif finding.auto_action == "remove_schedule":
        current = target.read_text(encoding="utf-8")
        updated = remove_schedule_block(current)
        if updated == current:
            raise RuntimeError(f"schedule block not found: {finding.workflow}")
        target.write_text(updated, encoding="utf-8")
    else:
        raise RuntimeError(f"unsupported autonomous action: {finding.auto_action}")

    proc = subprocess.run(
        ["git", "diff", "--name-only"], cwd=root, text=True, capture_output=True, check=True
    )
    changed = tuple(x.strip() for x in proc.stdout.splitlines() if x.strip())
    diff = subprocess.run(
        ["git", "diff", "--unified=0"], cwd=root, text=True, capture_output=True, check=True
    ).stdout
    decision = AutonomyGuard(root).analyze(list(changed), diff)
    if not decision.autonomous_allowed:
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=root, check=False)
        raise RuntimeError("owner escalation required: " + "; ".join(decision.reasons))
    return decision.level, changed


def write_report(root: Path, report: GovernanceReport, relative: str = "runtime/workflow_governance.json") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

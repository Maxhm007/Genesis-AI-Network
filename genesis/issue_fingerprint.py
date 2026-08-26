from __future__ import annotations

import hashlib
import json
import re


_TASK_TYPE_RE = re.compile(r"^- \*\*Task type:\*\* `([^`]+)`", re.MULTILINE)
_SOURCE_RE = re.compile(r"^- \*\*Source:\*\* `([^`]+)`", re.MULTILINE)
_TARGET_RE = re.compile(r"^- \*\*Target:\*\* `([^`]+)`", re.MULTILINE)
_OBJECTIVE_RE = re.compile(r"### Objective\n(.*?)(?:\n\n### Acceptance\n|\Z)", re.DOTALL)
_GENERATED_CAPABILITY_RE = re.compile(r"\bnamed\s+learned_[0-9a-f]{8,}\b", re.IGNORECASE)
_BENCHMARK_RETRY_RE = re.compile(r"\s+This is integration generation \d+\..*$", re.IGNORECASE | re.DOTALL)


def _normalized_objective(task_type: str, objective: str) -> str:
    task_type = str(task_type or "autonomous_task").strip().lower()
    text = str(objective or "")[:10000]
    if task_type == "benchmark_runner_integration":
        text = _BENCHMARK_RETRY_RE.sub("", text)
    if task_type == "capability_growth":
        text = text.split(" FAILURE_STRATEGY:", 1)[0]
    if task_type == "new_capability":
        text = _GENERATED_CAPABILITY_RE.sub("named learned_<generated>", text)
    return " ".join(text.split()).strip().lower()


def canonical_problem_fingerprint(*, task_type: str, source: str, target: str, objective: str) -> str:
    normalized_task_type = str(task_type or "autonomous_task").strip().lower()
    material = {
        "task_type": normalized_task_type,
        "source": str(source or "genesis").strip().lower(),
        "target": str(target or "").replace("\\", "/").strip().lower(),
        "objective": _normalized_objective(normalized_task_type, objective),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"genesis-objective:{digest[:32]}"


def canonical_task_fingerprint(task) -> str:
    payload = dict(getattr(task, "payload", {}) or {})
    task_type = str(payload.get("task_type") or "autonomous_task").strip() or "autonomous_task"
    source = str(payload.get("source") or "genesis").strip() or "genesis"
    target = str(payload.get("target_path") or "").strip()
    return canonical_problem_fingerprint(
        task_type=task_type,
        source=source,
        target=target,
        objective=str(getattr(task, "objective", "") or ""),
    )


def canonical_issue_fingerprint(body: str) -> str:
    text = str(body or "")
    task_type_match = _TASK_TYPE_RE.search(text)
    objective_match = _OBJECTIVE_RE.search(text)
    if task_type_match is None or objective_match is None:
        return ""
    source_match = _SOURCE_RE.search(text)
    target_match = _TARGET_RE.search(text)
    return canonical_problem_fingerprint(
        task_type=task_type_match.group(1),
        source=source_match.group(1) if source_match else "genesis",
        target=target_match.group(1) if target_match else "",
        objective=objective_match.group(1),
    )

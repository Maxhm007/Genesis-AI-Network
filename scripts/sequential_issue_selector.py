from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from genesis.issue_governor import issue_value_score
from genesis.issue_target import extract_issue_target

PROTECTED_TARGETS = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/issue_solver.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
}

ACTIVE_LABELS = {
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-priority-claim",
}

EXCLUDED_LABELS = {
    "genesis-superseded",
    "genesis-verified",
    "genesis-waiting-capability",
    "genesis-needs-human",
    "genesis-blocked",
    "genesis-solver-exhausted",
}

CONCRETE_REPAIR_LABELS = {
    "genesis-action-failure",
    "genesis-repair",
    "task3-failed-autonomy",
    "needs-repair-engine-improvement",
}


def _labels(issue: dict) -> set[str]:
    return {
        str(x.get("name") or "")
        for x in issue.get("labels") or []
        if isinstance(x, dict)
    }


def _age_hours(issue: dict, now: datetime) -> float:
    raw = str(issue.get("created_at") or issue.get("createdAt") or "")
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (now - created.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _blocked_issue_count(issue: dict) -> int:
    body = str(issue.get("body") or "")
    refs = re.findall(r"(?i)\b(?:blocks?|unlocks?)\s+#(\d+)\b", body)
    return len(set(refs))


def _severity(labels: set[str]) -> str:
    lowered = {x.lower() for x in labels}
    if lowered & {"critical", "severity-critical", "security-critical", "production-down"}:
        return "critical"
    if lowered & {"high", "severity-high", "priority-high"}:
        return "high"
    if lowered & {"low", "severity-low", "priority-low"}:
        return "low"
    return "medium"


def _retry_depth(issue: dict) -> int:
    labels = _labels(issue)
    depth = 0
    for label in labels:
        match = re.search(r"(?:attempt|retry)[-_ ]?(\d+)", label.lower())
        if match:
            depth = max(depth, int(match.group(1)))
    if "genesis-stuck-10x" in labels:
        depth = max(depth, 10)
    return depth


def _safe_target(issue: dict) -> str:
    body = str(issue.get("body") or "")
    target = extract_issue_target(body)
    if not target:
        return ""
    target = target.replace("\\", "/")
    if ".." in target or target in PROTECTED_TARGETS:
        return ""
    if not target.startswith("genesis/") or not target.endswith(".py"):
        return ""
    if not Path(target).is_file():
        return ""
    return target


def classify(issue: dict) -> str:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    labels = _labels(issue)
    lower_title = title.lower()
    lower_body = body.lower()

    if (
        lower_title.startswith("genesis action failure:")
        or lower_title.startswith("[genesis action failure]")
        or "syntax error" in lower_body
    ):
        return "urgent"
    if lower_title.startswith(("[genesis detected]", "[genesis repair]")) or labels & CONCRETE_REPAIR_LABELS:
        return "repair"
    return "general"


def candidate(issue: dict, *, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    if issue.get("pull_request"):
        return None
    number = int(issue.get("number") or 0)
    if number <= 1:
        return None

    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    labels = _labels(issue)
    lower_title = title.lower()
    lower_body = body.lower()

    if lower_title.startswith(("genesis chat:", "[genesis hourly report]", "[genesis gene chat]")):
        return None
    if "persistent github-native reporting channel" in lower_body:
        return None
    if labels & ACTIVE_LABELS or labels & EXCLUDED_LABELS:
        return None

    kind = classify(issue)
    target = _safe_target(issue)
    if kind not in {"urgent"} and not target:
        return None

    retry_depth = _retry_depth(issue)
    owner_priority = 1.0 if labels & {"owner-priority", "owner_priority", "user-priority"} else 0.0
    reuse_value = 0.9 if labels & {"genesis-capability", "genesis-capability-blocker", "capability-blocker"} else 0.7
    success_probability = max(0.2, 0.9 - 0.07 * retry_depth)

    value = issue_value_score(
        severity=_severity(labels),
        blocked_issues=_blocked_issue_count(issue),
        age_hours=_age_hours(issue, now),
        reuse_value=reuse_value,
        owner_priority=owner_priority,
        retry_depth=retry_depth,
        success_probability=success_probability,
    )

    lane_bonus = {"urgent": 25.0, "repair": 10.0, "general": 0.0}[kind]
    score = min(125.0, value.score + lane_bonus)

    return {
        "number": number,
        "kind": kind,
        "target": target,
        "score": round(score, 3),
        "base_score": value.score,
        "lane_bonus": lane_bonus,
        "breakdown": value.breakdown,
        "created_at": str(issue.get("created_at") or ""),
    }


def select(issues: list[dict], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ranked = [row for issue in issues if (row := candidate(issue, now=now)) is not None]
    ranked.sort(key=lambda row: (-float(row["score"]), row["created_at"], int(row["number"])))
    return {
        "selected": ranked[0] if ranked else None,
        "ranked": ranked[:20],
        "eligible_count": len(ranked),
    }


def main() -> int:
    payload = json.load(__import__("sys").stdin)
    if not isinstance(payload, list):
        raise SystemExit("expected a JSON list of issues")
    print(json.dumps(select(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

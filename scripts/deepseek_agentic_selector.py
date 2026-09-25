from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from genesis.anti_stuck import (
    Attempt,
    attempt_history,
    attempt_marker,
    has_state_marker,
    material_state_token,
    materially_equivalent_attempt,
    next_lane_strategy,
    state_marker,
)
from genesis.issue_lifecycle import local_claim_block_reason


ROOT = Path(__file__).resolve().parents[1]
DEEPSEEK_STRATEGIES = ("evidence_first", "alternative_implementation", "diagnostic_reframe")

CONFLICT_LABELS = {
    "genesis-repair-in-progress",
    "genesis-claimed",
    "genesis-working",
    "genesis-validating",
    "genesis-verifying",
    "genesis-deepseek-working",
}

UNSUITABLE_LABELS = {
    "genesis-needs-human",
    "genesis-waiting-capability",
    "genesis-blocked",
}

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
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}

TARGET_RE = re.compile(r"\b((?:genesis|scripts)/[A-Za-z0-9_./-]+\.py)\b")


def _labels(issue: dict) -> set[str]:
    rows = issue.get("labels") or []
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip()
        else:
            name = str(row).strip()
        if name:
            out.add(name)
    return out


def target_from(issue: dict) -> str:
    text = f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    for match in TARGET_RE.findall(text):
        target = match.strip().replace("\\", "/")
        if target and target not in PROTECTED_TARGETS:
            return target
    return ""


def score(issue: dict, *, allow_agentic_handoff: bool = False) -> tuple[int, dict]:
    lifecycle_block = local_claim_block_reason(issue)
    if lifecycle_block:
        return (-10_000, {"reason": f"lifecycle_{lifecycle_block}"})

    labels = _labels(issue)
    conflicts = labels & CONFLICT_LABELS
    if allow_agentic_handoff:
        conflicts -= {"genesis-repair-in-progress"}
    if conflicts or labels & UNSUITABLE_LABELS:
        return (-10_000, {"reason": "conflicting_or_unsuitable_label"})

    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    text = f"{title}\n{body}".lower()
    target = target_from(issue)
    if not target:
        return (-10_000, {"reason": "no_safe_explicit_python_target"})

    value = 0
    reasons: list[str] = []
    if target.startswith("genesis/"):
        value += 30
        reasons.append("genesis_python_target")
    elif target.startswith("scripts/"):
        value += 22
        reasons.append("script_python_target")

    if "acceptance" in text:
        value += 16
        reasons.append("explicit_acceptance")
    if any(word in text for word in ("fix", "repair", "bug", "fails", "failure", "incorrect", "reliability")):
        value += 18
        reasons.append("repair_shaped")
    if any(word in text for word in ("test", "pytest", "regression")):
        value += 10
        reasons.append("testable")
    if "self upgrade" in text or "new capability" in text:
        value += 6
        reasons.append("bounded_upgrade")
    if "dashboard" in text:
        value += 4
        reasons.append("bounded_dashboard")
    if "agentic lab" in text:
        value += 4
        reasons.append("agentic_context")
    if "owner action required" in text and "true" in text:
        value -= 50
        reasons.append("owner_action_penalty")
    if any(word in text for word in ("secret", "credential", "signing key", "private key")):
        value -= 80
        reasons.append("sensitive_boundary_penalty")

    return value, {"target": target, "reasons": reasons}


def select(issues: list[dict], *, allow_agentic_handoff: bool = False) -> dict | None:
    ranked: list[tuple[int, int, dict, dict]] = []
    for issue in issues:
        value, detail = score(issue, allow_agentic_handoff=allow_agentic_handoff)
        if value < 0:
            continue
        number = int(issue.get("number") or issue.get("issue_number") or 0)
        ranked.append((value, -number, issue, detail))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    value, _, issue, detail = ranked[0]
    return {
        "number": int(issue.get("number") or issue.get("issue_number") or 0),
        "title": str(issue.get("title") or ""),
        "score": value,
        **detail,
    }


def plan_deepseek_attempt(issue: dict, comments: list[dict], target: str) -> dict:
    token = material_state_token(issue, target, comments, root=ROOT)
    history = attempt_history(comments, token, target)
    strategy = next_lane_strategy(
        history,
        provider="deepseek",
        gene="Gene 003",
        target=target,
        strategies=DEEPSEEK_STRATEGIES,
    )
    if not strategy:
        return {
            "eligible": False,
            "reason": "deepseek_strategy_epoch_exhausted",
            "state_token": token,
            "needs_state_marker": not has_state_marker(comments, token),
        }

    candidate = Attempt(
        strategy=strategy,
        provider="deepseek",
        gene="Gene 003",
        target=target,
    )
    if materially_equivalent_attempt(history, candidate):
        return {
            "eligible": False,
            "reason": "materially_equivalent_attempt",
            "state_token": token,
            "needs_state_marker": not has_state_marker(comments, token),
        }

    return {
        "eligible": True,
        "strategy": strategy,
        "provider": "deepseek",
        "gene": "Gene 003",
        "state_token": token,
        "needs_state_marker": not has_state_marker(comments, token),
        "state_marker": state_marker(token),
        "attempt_marker": attempt_marker(candidate),
        "attempt_number": len([row for row in history if row.provider.lower() == "deepseek"]) + 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Select or plan work for the DeepSeek agentic solver")
    parser.add_argument("--issues-json", type=Path)
    parser.add_argument("--issue-json", type=Path)
    parser.add_argument("--comments-json", type=Path)
    parser.add_argument("--target", default="")
    parser.add_argument("--allow-agentic-handoff", action="store_true")
    args = parser.parse_args()

    if args.issue_json and args.comments_json:
        issue_payload = json.loads(args.issue_json.read_text(encoding="utf-8"))
        comments_payload = json.loads(args.comments_json.read_text(encoding="utf-8"))
        if not isinstance(issue_payload, dict) or not isinstance(comments_payload, list):
            raise SystemExit("issue JSON must be an object and comments JSON must be a list")
        print(json.dumps(plan_deepseek_attempt(issue_payload, comments_payload, args.target), sort_keys=True))
        return

    if not args.issues_json:
        raise SystemExit("--issues-json is required for selection mode")
    payload = json.loads(args.issues_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("issues JSON must be a list")
    result = select(payload, allow_agentic_handoff=args.allow_agentic_handoff)
    print(json.dumps(result or {}, sort_keys=True))


if __name__ == "__main__":
    main()

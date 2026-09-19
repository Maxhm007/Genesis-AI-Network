from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


STATE_PREFIX = "<!-- genesis-anti-stuck-state:"
ATTEMPT_PREFIX = "<!-- genesis-anti-stuck-attempt:"
CAPABILITY_RELEASE_PREFIX = "<!-- genesis-agentic-capability-release:"
AGENTIC_STRATEGY_PREFIX = "<!-- genesis-agentic-strategy:"
AGENTIC_RESULT_PREFIX = "<!-- genesis-agentic-strategy-result:"
DEEPSEEK_ATTEMPT_PREFIX = "<!-- genesis-deepseek-attempt:"
DEEPSEEK_RESULT_PREFIX = "<!-- genesis-deepseek-result:"

DEFAULT_PROVIDER_SWITCH_AFTER = 2
DEFAULT_CAPABILITY_AFTER_DISTINCT_FAILURES = 5


@dataclass(frozen=True)
class Attempt:
    strategy: str
    provider: str
    gene: str
    target: str
    blocker: str = ""
    result: str = ""

    @property
    def material_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.strategy.strip().lower(),
            self.provider.strip().lower(),
            self.gene.strip().lower(),
            self.target.strip().lower(),
            self.blocker.strip().lower(),
        )


@dataclass(frozen=True)
class AntiStuckDecision:
    action: str
    reason: str
    provider: str = ""
    gene: str = ""


def _body(row: dict) -> str:
    return str(row.get("body") or "")


def _marker_value(body: str, prefix: str) -> str:
    if not body.startswith(prefix):
        return ""
    return body[len(prefix):].split("-->", 1)[0].strip()


def material_state_token(
    issue: dict,
    target: str,
    comments: Iterable[dict],
    *,
    root: Path | None = None,
) -> str:
    """Fingerprint only material state that should re-arm failed strategies."""
    digest = hashlib.sha256()
    digest.update(str(issue.get("body") or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(target or "").strip().encode("utf-8"))
    digest.update(b"\0")

    if root is not None and target:
        path = (Path(root) / target).resolve()
        try:
            if path.is_file() and Path(root).resolve() in path.parents:
                digest.update(path.read_bytes())
        except OSError:
            pass

    releases = [
        _marker_value(_body(row), CAPABILITY_RELEASE_PREFIX)
        for row in comments
        if _body(row).startswith(CAPABILITY_RELEASE_PREFIX)
    ]
    digest.update(b"\0")
    digest.update("|".join(releases).encode("utf-8"))
    return digest.hexdigest()[:20]


def state_marker(token: str) -> str:
    return f"{STATE_PREFIX}{str(token).strip()} -->"


def attempt_marker(attempt: Attempt) -> str:
    payload = json.dumps(
        {
            "strategy": attempt.strategy,
            "provider": attempt.provider,
            "gene": attempt.gene,
            "target": attempt.target,
            "blocker": attempt.blocker,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{ATTEMPT_PREFIX}{payload} -->"


def current_epoch_comments(comments: Iterable[dict], token: str) -> list[dict]:
    rows = list(comments)
    marker = state_marker(token)
    latest = -1
    for index, row in enumerate(rows):
        if marker in _body(row):
            latest = index
    return rows[latest + 1 :] if latest >= 0 else []


def has_state_marker(comments: Iterable[dict], token: str) -> bool:
    marker = state_marker(token)
    return any(marker in _body(row) for row in comments)


def _parse_explicit_attempt(body: str) -> Attempt | None:
    if not body.startswith(ATTEMPT_PREFIX):
        return None
    raw = body[len(ATTEMPT_PREFIX):].split("-->", 1)[0].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    strategy = str(payload.get("strategy") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    gene = str(payload.get("gene") or "").strip()
    target = str(payload.get("target") or "").strip()
    blocker = str(payload.get("blocker") or "").strip()
    if not strategy or not provider or not gene or not target:
        return None
    return Attempt(strategy, provider, gene, target, blocker)


def attempt_history(comments: Iterable[dict], token: str, target: str) -> tuple[Attempt, ...]:
    """Read one state epoch into a cross-lane attempt history."""
    rows = current_epoch_comments(comments, token)
    attempts: list[Attempt] = []
    explicit = False

    for row in rows:
        body = _body(row)
        parsed = _parse_explicit_attempt(body)
        if parsed is not None:
            explicit = True
            attempts.append(parsed)
            continue

        if explicit:
            continue

        if body.startswith(AGENTIC_STRATEGY_PREFIX):
            strategy = _marker_value(body, AGENTIC_STRATEGY_PREFIX)
            provider = "qwen3" if strategy == "qwen3_fallback" else "agentic-default"
            attempts.append(
                Attempt(
                    strategy=strategy,
                    provider=provider,
                    gene="Gene 0",
                    target=target,
                )
            )
            continue

        if body.startswith(DEEPSEEK_ATTEMPT_PREFIX):
            strategy_match = re.search(r"strategy\s+\x60([^\x60]+)\x60", body)
            strategy = strategy_match.group(1).strip() if strategy_match else "deepseek_attempt"
            attempts.append(
                Attempt(
                    strategy=strategy,
                    provider="deepseek",
                    gene="Gene 003",
                    target=target,
                )
            )

    mutable = [attempt.__dict__.copy() for attempt in attempts]
    for row in rows:
        body = _body(row)
        if body.startswith(AGENTIC_RESULT_PREFIX):
            strategy = _marker_value(body, AGENTIC_RESULT_PREFIX)
            status_match = re.search(r"repair status:\s*\x60([^\x60]+)\x60", body)
            status = status_match.group(1).strip() if status_match else "failed"
            for record in reversed(mutable):
                if record["strategy"] == strategy and not record["result"]:
                    record["result"] = status
                    record["blocker"] = status
                    break
        elif body.startswith(DEEPSEEK_RESULT_PREFIX):
            status_match = re.search(r"repair status:\s*\x60([^\x60]+)\x60", body)
            status = status_match.group(1).strip() if status_match else _marker_value(body, DEEPSEEK_RESULT_PREFIX)
            for record in reversed(mutable):
                if record["provider"] == "deepseek" and not record["result"]:
                    record["result"] = status
                    record["blocker"] = status
                    break

    return tuple(Attempt(**record) for record in mutable)


def materially_equivalent_attempt(history: Iterable[Attempt], candidate: Attempt) -> bool:
    key = candidate.material_key
    return any(attempt.material_key == key for attempt in history)


def failed_attempts(history: Iterable[Attempt]) -> tuple[Attempt, ...]:
    success = {"solved", "verified", "candidate_promoted", "complete", "completed"}
    return tuple(
        attempt
        for attempt in history
        if attempt.result and attempt.result.strip().lower() not in success
    )


def anti_stuck_decision(
    history: Iterable[Attempt],
    *,
    compatible_lanes: tuple[tuple[str, str], ...] = (
        ("agentic-default", "Gene 0"),
        ("qwen3", "Gene 0"),
        ("deepseek", "Gene 003"),
    ),
    provider_switch_after: int = DEFAULT_PROVIDER_SWITCH_AFTER,
    capability_after_distinct_failures: int = DEFAULT_CAPABILITY_AFTER_DISTINCT_FAILURES,
) -> AntiStuckDecision:
    rows = tuple(history)
    failures = failed_attempts(rows)
    distinct_failure_keys = {attempt.material_key for attempt in failures}

    if len(distinct_failure_keys) >= int(capability_after_distinct_failures):
        return AntiStuckDecision("capability", "distinct_failure_budget_exhausted")

    if len(distinct_failure_keys) < int(provider_switch_after):
        return AntiStuckDecision("continue", "strategy_budget_available")

    failed_lanes = {(attempt.provider.lower(), attempt.gene.lower()) for attempt in failures}
    for provider, gene in compatible_lanes:
        if (provider.lower(), gene.lower()) not in failed_lanes:
            return AntiStuckDecision(
                "switch_lane",
                "provider_or_gene_rotation_required",
                provider=provider,
                gene=gene,
            )

    return AntiStuckDecision("continue", "all_compatible_lanes_sampled")


def should_release_worker(labels: Iterable[str]) -> bool:
    values = {str(label).strip() for label in labels}
    return bool(
        values
        & {
            "genesis-waiting-capability",
            "genesis-needs-human",
            "genesis-superseded",
            "genesis-verified",
        }
    )

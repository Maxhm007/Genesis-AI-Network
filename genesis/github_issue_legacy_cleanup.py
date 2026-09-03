from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .github_issue_cleanup import (
    _close_issue,
    _github_request,
    _issue_number,
    _list_open_issues,
    _managed_key,
    _protected_issue,
)
from .github_issue_task_router import issue_authority_enabled


GithubRequester = Callable[[str, str, dict | None], object | None]
FIELD_RE = re.compile(
    r"^\s*-\s*\*\*(?P<name>Operational issue|Module|Evidence):\*\*\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _normalize(value: str) -> str:
    value = value.replace("`", " ")
    return " ".join(value.strip().lower().split())


def _managed_fields(issue: dict) -> tuple[str, str, str, str] | None:
    marker = _managed_key(issue)
    if marker is None:
        return None
    kind, _fingerprint = marker
    body = str(issue.get("body") or "")
    fields: dict[str, str] = {}
    for match in FIELD_RE.finditer(body):
        fields[match.group("name").lower()] = _normalize(match.group("value"))

    problem = fields.get("operational issue", "")
    if not problem and kind == "genesis-ops":
        title = str(issue.get("title") or "").strip()
        prefix = "[Genesis Ops]"
        if title.startswith(prefix):
            problem = _normalize(title[len(prefix):])

    module = fields.get("module", "")
    evidence = fields.get("evidence", "")
    if not problem or not module or not evidence:
        return None
    return kind, problem, module, evidence


def cleanup_legacy_managed_duplicates(
    root: Path,
    *,
    requester: GithubRequester | None = None,
) -> dict:
    """Close legacy managed records only when explicit semantics prove supersession.

    This supplements exact marker/fingerprint cleanup for old Genesis-managed Ops and
    Escalation records whose marker format changed over time. It never uses age or
    title similarity alone: managed kind, operational problem, module, and evidence
    must all match exactly after normalization. Protected/control Issues are ignored.
    """
    root = Path(root).resolve()
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    report_path = runtime / "github_issue_legacy_cleanup.json"
    explicit_requester = requester is not None

    result = {
        "status": "ok",
        "enforced": bool(explicit_requester or issue_authority_enabled(root)),
        "scanned": 0,
        "closed": [],
        "kept_current": [],
        "skipped_protected": [],
        "blocked": [],
    }
    if not result["enforced"]:
        result["status"] = "not_repository_runtime"
        result["reason"] = "temporary/non-repository runtime; real GitHub Issue mutations are disabled"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    requester = requester or _github_request
    issues = _list_open_issues(requester)
    if issues is None:
        result["status"] = "blocked"
        result["blocked"].append({"reason": "github_open_issue_list_unavailable"})
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    result["scanned"] = len(issues)
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for issue in issues:
        number = _issue_number(issue)
        if number <= 0:
            continue
        if _protected_issue(issue):
            result["skipped_protected"].append(number)
            continue
        key = _managed_fields(issue)
        if key is not None:
            groups.setdefault(key, []).append(issue)

    for key, rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        newest = max(rows, key=_issue_number)
        newest_number = _issue_number(newest)
        result["kept_current"].append(
            {
                "github_issue_number": newest_number,
                "managed_kind": key[0],
                "problem": key[1],
                "module": key[2],
                "evidence": key[3],
            }
        )
        for issue in sorted(rows, key=_issue_number):
            number = _issue_number(issue)
            if number == newest_number:
                continue
            marker = _managed_key(issue)
            current_marker = _managed_key(newest)
            if marker == current_marker:
                continue
            closed = _close_issue(
                requester,
                issue,
                reason=(
                    f"legacy_semantic_supersession:{key[0]}:"
                    f"problem={key[1]}:module={key[2]}:evidence={key[3]}:"
                    f"newer_issue=#{newest_number}"
                ),
            )
            if closed is None:
                result["blocked"].append(
                    {"github_issue_number": number, "reason": "legacy_semantic_close_failed"}
                )
            else:
                result["closed"].append(closed)

    if result["blocked"]:
        result["status"] = "partial" if result["closed"] else "blocked"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

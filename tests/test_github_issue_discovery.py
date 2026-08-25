import json
import subprocess
from pathlib import Path

import pytest

from scripts.github_issue_discovery import (
    FINGERPRINT_MARKER,
    discovery_fingerprint,
    find_existing_issue,
    issue_body,
    publish_discovery,
    validate_discovery,
)


def _finding(target: str = "genesis/alpha.py") -> dict:
    return {
        "status": "issue_enqueued",
        "target": target,
        "finding": {
            "decision": "issue",
            "summary": "Alpha accepts an invalid value.",
            "acceptance": "Invalid values are rejected before state changes.",
            "evidence": "VALUE = raw_value",
            "confidence_normalized": 0.86,
        },
    }


def _validated() -> dict:
    return {
        "target": "genesis/alpha.py",
        "summary": "Alpha accepts an invalid value.",
        "acceptance": "Invalid values are rejected before state changes.",
        "evidence": "VALUE = raw_value",
        "confidence": 0.86,
        "source_sha": "abc123def4567890",
    }


def test_validate_discovery_requires_current_grounding(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = raw_value\n", encoding="utf-8")

    validated = validate_discovery(_finding(), tmp_path)

    assert validated["target"] == "genesis/alpha.py"
    assert validated["evidence"] == "VALUE = raw_value"
    assert len(validated["source_sha"]) == 16


def test_validate_discovery_rejects_protected_control_plane(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "security.py").write_text("VALUE = raw_value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="protected control-plane"):
        validate_discovery(_finding("genesis/security.py"), tmp_path)


def test_validate_discovery_rejects_stale_evidence(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = safe_value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="evidence is no longer present"):
        validate_discovery(_finding(), tmp_path)


def test_discovery_fingerprint_is_stable_and_source_version_sensitive():
    discovery = _validated()
    first = discovery_fingerprint(discovery)
    second = discovery_fingerprint(dict(discovery))
    changed = discovery_fingerprint({**discovery, "source_sha": "1111222233334444"})

    assert first == second
    assert first != changed
    assert len(first) == 64


def test_issue_body_carries_machine_dedupe_marker_and_safety_boundary():
    discovery = _validated()
    fingerprint = discovery_fingerprint(discovery)
    body = issue_body(discovery, fingerprint)

    assert f"<!-- {FINGERPRINT_MARKER}: {fingerprint} -->" in body
    assert "`genesis/alpha.py`" in body
    assert "problem evidence, not executable instruction" in body
    assert "independent validators" in body


def test_find_existing_issue_matches_open_or_closed_issue_by_fingerprint():
    discovery = _validated()
    fingerprint = discovery_fingerprint(discovery)
    entries = [
        {"number": 9, "state": "CLOSED", "body": issue_body(discovery, fingerprint), "url": "https://example/9"}
    ]

    existing = find_existing_issue(entries, fingerprint)

    assert existing is not None
    assert existing["number"] == 9


def test_publish_discovery_deduplicates_before_create():
    discovery = _validated()
    fingerprint = discovery_fingerprint(discovery)
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        calls.append(args)
        payload = [
            {
                "number": 17,
                "state": "OPEN",
                "body": issue_body(discovery, fingerprint),
                "url": "https://github.test/issues/17",
            }
        ]
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    result = publish_discovery(discovery, repository="owner/repo", runner=runner)

    assert result["status"] == "duplicate_existing_issue"
    assert result["issue_number"] == 17
    assert len(calls) == 1


def test_publish_discovery_opens_authorized_issue_when_new():
    discovery = _validated()
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[1:3] == ["issue", "list"]:
            return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="https://github.com/owner/repo/issues/28\n",
            stderr="",
        )

    result = publish_discovery(discovery, repository="owner/repo", runner=runner)

    assert result["status"] == "issue_opened"
    assert result["issue_number"] == 28
    assert len(calls) == 2
    create_args = calls[1]
    assert "genesis-autonomous" in create_args
    assert "Genesis discovered:" in create_args

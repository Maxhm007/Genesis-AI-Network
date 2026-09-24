from __future__ import annotations

from scripts import agentic_issue_opening_authority as authority


def candidate(**overrides):
    payload = {
        "schema": "genesis.agentic-issue-candidate.v1",
        "lane": "github-issue-discovery",
        "title": "Genesis discovered: bounded test defect",
        "body": (
            "<!-- genesis-issue-opening-manager -->\n"
            "Genesis-Opening-Lane: github-issue-discovery\n"
            "- **Target:** `genesis/example.py`\n"
            "### Objective\nFix one bounded defect."
        ),
        "labels": ["genesis-task"],
        "severity": "medium",
        "value_score": 72.0,
        "bypass_backlog": False,
        "candidate_fingerprint": "abc123",
    }
    payload.update(overrides)
    return payload


def test_normalize_candidate_adds_agentic_authority_labels():
    row = authority.normalize_candidate(candidate())
    assert "genesis-autonomous" in row["labels"]
    assert "agentic-lab" in row["labels"]
    assert row["lane"] == "github-issue-discovery"


def test_duplicate_candidate_is_not_created(monkeypatch):
    monkeypatch.setattr(
        authority,
        "fetch_issues",
        lambda *_args, **_kwargs: [{
            "number": 42,
            "state": "open",
            "title": "Genesis discovered: bounded test defect",
            "body": (
                "- **Target:** `genesis/example.py`\n"
                "### Objective\nFix one bounded defect."
            ),
            "html_url": "https://example.test/issues/42",
        }],
    )
    calls = []
    monkeypatch.setattr(authority, "_request", lambda *args, **kwargs: calls.append((args, kwargs)) or {})

    result = authority.run("owner/repo", "token", candidate())

    assert result["status"] == "duplicate"
    assert result["issue_number"] == 42
    assert calls == []


def test_publish_candidate_is_created_only_by_authority_and_wakes_agentic_lab(monkeypatch):
    monkeypatch.setattr(authority, "fetch_issues", lambda *_args, **_kwargs: [])
    calls = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "POST" and path == "/issues":
            return {
                "number": 77,
                "html_url": "https://example.test/issues/77",
            }
        return {}

    monkeypatch.setattr(authority, "_request", fake_request)
    result = authority.run("owner/repo", "token", candidate())

    assert result["status"] == "opened"
    assert result["issue_number"] == 77
    issue_call = next(call for call in calls if call[1] == "/issues")
    assert "agentic-lab" in issue_call[2]["labels"]
    assert "genesis-autonomous" in issue_call[2]["labels"]
    assert "genesis-agentic-opening-authority" in issue_call[2]["body"]
    assert any(
        path == "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches"
        for _method, path, _payload in calls
    )

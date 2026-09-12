from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "park_exhausted_agentic_issues.py"
    spec = importlib.util.spec_from_file_location("park_exhausted_agentic_issues", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_waiting_issue_is_reactivated_into_agentic_lab(monkeypatch):
    module = _load_module()
    calls: list[tuple[str, str, object]] = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    issue = {
        "number": 707,
        "labels": [
            {"name": "genesis-waiting-user"},
            {"name": "genesis-repair-in-progress"},
            {"name": "genesis-validating"},
            {"name": "agentic-lab"},
        ],
    }

    assert module.park_issue("owner/repo", "token", issue) is True
    assert any(method == "DELETE" and path.endswith("/labels/genesis-waiting-user") for method, path, _ in calls)
    assert any(
        method == "POST"
        and path.endswith("/issues/707/labels")
        and payload == {"labels": ["agentic-lab", "genesis-autonomous", "genesis-solver-exhausted"]}
        for method, path, payload in calls
    )
    assert any(
        method == "POST"
        and path.endswith("/issues/707/comments")
        and "stays OPEN" in str(payload)
        for method, path, payload in calls
    )


def test_full_agentic_strategy_rotation_retries_instead_of_parking(monkeypatch):
    module = _load_module()
    calls: list[tuple[str, str, object]] = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module, "request", fake_request)
    monkeypatch.setattr(
        module,
        "comments",
        lambda repository, token, number: [
            {"body": "<!-- genesis-agentic-strategy:evidence_first -->"},
            {"body": "<!-- genesis-agentic-strategy-result:evidence_first --> failed"},
            {"body": "<!-- genesis-agentic-strategy:alternative_implementation -->"},
            {"body": "<!-- genesis-agentic-strategy-result:alternative_implementation --> failed"},
            {"body": "<!-- genesis-agentic-strategy:diagnostic_reframe -->"},
            {"body": "<!-- genesis-agentic-strategy-result:diagnostic_reframe --> failed"},
            {"body": "<!-- genesis-agentic-strategy:dependency_diagnosis -->"},
            {"body": "<!-- genesis-agentic-strategy-result:dependency_diagnosis --> failed"},
        ],
    )

    issue = {
        "number": 708,
        "labels": [
            {"name": "agentic-lab"},
            {"name": "genesis-autonomous"},
            {"name": "genesis-solver-exhausted"},
        ],
    }

    assert module.park_issue("owner/repo", "token", issue) is True
    assert not any(
        method == "POST"
        and path.endswith("/issues/708/labels")
        and payload
        and "genesis-waiting-user" in payload.get("labels", [])
        for method, path, payload in calls
    )
    assert any(
        method == "POST"
        and path.endswith("/issues/708/labels")
        and payload == {"labels": ["agentic-lab", "genesis-autonomous", "genesis-solver-exhausted"]}
        for method, path, payload in calls
    )
    assert any(
        method == "POST"
        and path.endswith("/issues/708/comments")
        and "remains OPEN" in str(payload)
        and "does not close or park" in str(payload)
        for method, path, payload in calls
    )

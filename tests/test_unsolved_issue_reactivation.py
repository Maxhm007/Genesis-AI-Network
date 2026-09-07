from pathlib import Path

import scripts.unsolved_issue_reactivation as module


WORKFLOW = Path(".github/workflows/genesis-unsolved-issue-reactivation.yml")


def _issue(*labels: str, state: str = "closed") -> dict:
    return {
        "number": 42,
        "state": state,
        "labels": [{"name": name} for name in labels],
    }


def test_solver_exhaustion_is_reopened_for_agentic_strategy_rotation(monkeypatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/42":
            return _issue("genesis-solver-exhausted", "genesis-deferred")
        if method == "GET" and path == "/issues/42/comments?per_page=100":
            return [{"body": "Genesis bounded repair did not promote a verified change in worker run 1"}]
        if method == "PATCH" and path == "/issues/42":
            return {"number": 42, "state": "open"}
        return {}

    monkeypatch.setattr(module, "request", fake_request)
    result = module.reactivate("owner/repo", "token", 42)

    assert result["status"] == "reactivated"
    assert any(method == "PATCH" and path == "/issues/42" and payload == {"state": "open"} for method, path, payload in calls)
    assert any(method == "POST" and path == "/actions/workflows/genesis-agentic-lab-recovery.yml/dispatches" for method, path, _ in calls)
    assert any(method == "POST" and path == "/issues/42/labels" and "agentic-lab" in (payload or {}).get("labels", []) for method, path, payload in calls)


def test_verified_or_superseded_closures_remain_authoritative(monkeypatch) -> None:
    for label, expected in (("genesis-verified", "verified_closure"), ("genesis-superseded", "superseded_closure")):
        monkeypatch.setattr(module, "request", lambda repository, token, method, path, payload=None, label=label: _issue("genesis-solver-exhausted", label))
        result = module.reactivate("owner/repo", "token", 42)
        assert result == {"status": "ignored", "issue_number": 42, "reason": expected}


def test_closed_issue_without_genesis_failure_evidence_is_not_reopened(monkeypatch) -> None:
    def fake_request(repository, token, method, path, payload=None):
        if method == "GET" and path == "/issues/42":
            return _issue("genesis-solver-exhausted")
        if method == "GET" and path == "/issues/42/comments?per_page=100":
            return [{"body": "Maintainer closed this manually."}]
        raise AssertionError(f"unexpected mutation: {method} {path}")

    monkeypatch.setattr(module, "request", fake_request)
    result = module.reactivate("owner/repo", "token", 42)
    assert result["reason"] == "no_solver_failure_evidence"


def test_workflow_only_auto_reacts_to_github_actions_closures() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "types: [closed]" in text
    assert "github.actor == 'github-actions[bot]'" in text
    assert "scripts/unsolved_issue_reactivation.py" in text
    assert "actions: write" in text

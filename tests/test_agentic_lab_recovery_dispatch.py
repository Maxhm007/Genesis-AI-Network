import scripts.agentic_lab_recovery_dispatch as module


def _issue(number: int, state: str = "open") -> dict:
    return {
        "number": number,
        "state": state,
        "body": "- **Target:** `genesis/example.py`\n",
        "labels": [{"name": "agentic-lab"}],
    }


def test_agentic_discovery_queries_only_open_issues(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path))
        return []

    monkeypatch.setattr(module, "request", fake_request)

    assert module.open_agentic_issues("owner/repo", "token") == []
    assert calls
    assert all("state=open" in path for method, path in calls if method == "GET")
    assert not any("state=all" in path for method, path in calls if method == "GET")


def test_closed_agentic_issue_is_never_reopened_or_dispatched(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [_issue(42, "closed")])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return []

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result == {"status": "idle", "reason": "no_safely_routable_agentic_issue"}
    assert not any(method == "PATCH" and path == "/issues/42" for method, path, _ in calls)
    assert not any("/actions/workflows/" in path for _, path, _ in calls)


def test_open_agentic_issue_still_dispatches_without_state_patch(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [_issue(43, "open")])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/43/comments?per_page=100":
            return []
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "dispatched"
    assert result["issue_number"] == 43
    assert result["workflow"] == "genesis-bounded-repair-worker.yml"
    assert not any(method == "PATCH" and path == "/issues/43" for method, path, _ in calls)
    assert any(
        method == "POST" and path == "/actions/workflows/genesis-bounded-repair-worker.yml/dispatches"
        for method, path, _ in calls
    )

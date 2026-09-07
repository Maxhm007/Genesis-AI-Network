import scripts.agentic_lab_recovery_dispatch as module


def _issue(number: int, state: str = "open", *, body: str | None = None, extra_labels: tuple[str, ...] = ()) -> dict:
    return {
        "number": number,
        "state": state,
        "body": body or "- **Target:** `genesis/example.py`\n",
        "labels": [{"name": "agentic-lab"}, *({"name": label} for label in extra_labels)],
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


def test_open_agentic_issue_dispatches_first_materially_different_strategy(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [_issue(43, "open")])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/43/comments?per_page=100":
            return []
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "dispatched"
    assert result["issue_number"] == 43
    assert result["strategy"] == "evidence_first"
    assert result["workflow"] == "genesis-agentic-strategy-worker.yml"
    assert any(
        method == "POST"
        and path == "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches"
        and payload == {"ref": "main", "inputs": {"issue_number": "43", "strategy": "evidence_first"}}
        for method, path, payload in calls
    )


def test_failed_strategy_rotates_to_next_strategy(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(44)
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nfirst method"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `repair_failed_validation`"},
    ]
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/44/comments?per_page=100":
            return comments
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["strategy"] == "alternative_implementation"


def test_capability_gap_creates_dependency_and_pauses_parent(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(45)
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nfirst method"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `retry_pending_capability`"},
    ]
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/45/comments?per_page=100":
            return comments
        if method == "GET" and path.startswith("/issues?state=all"):
            return []
        if method == "POST" and path == "/issues":
            return {"number": 88, "body": payload["body"], "state": "open", "labels": []}
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "waiting_capability"
    assert result["capability_issue"] == 88
    assert any(method == "POST" and path == "/issues" for method, path, _ in calls)
    assert not any("genesis-agentic-strategy-worker.yml/dispatches" in path for _, path, _ in calls)


def test_capability_issue_does_not_spawn_infinite_capability_chain(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(
        46,
        body=(
            "<!-- genesis-capability-work:abc123 -->\n"
            "- **Target:** `genesis/github_issue_capability_builder.py`\n"
        ),
    )
    comments = []
    for strategy in module.STRATEGIES:
        comments.append({"body": f"<!-- genesis-agentic-strategy:{strategy} -->\nmethod"})
        comments.append({"body": f"<!-- genesis-agentic-strategy-result:{strategy} -->\nrepair status: `repair_failed_validation`"})
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/46/comments?per_page=100":
            return comments
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "needs_human"
    assert not any(method == "POST" and path == "/issues" for method, path, _ in calls)

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


def test_capability_issue_switches_provider_before_human_escalation(monkeypatch):
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
        if method == "POST" and path == "/issues/46/comments":
            comments.append({"body": payload["body"]})
            return {}
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "dispatched"
    assert result["provider"] == "qwen3"
    assert result["strategy"] == "qwen3_fallback"
    assert not any(method == "POST" and path == "/issues" for method, path, _ in calls)


def test_agentic_switches_to_deepseek_after_qwen3_failure(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(49)
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `failed`"},
        {"body": "<!-- genesis-agentic-strategy:alternative_implementation -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:alternative_implementation -->\nrepair status: `failed`"},
        {"body": "<!-- genesis-agentic-strategy:qwen3_fallback -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:qwen3_fallback -->\nrepair status: `failed`"},
    ]
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/49/comments?per_page=100":
            return comments
        if method == "POST" and path == "/issues/49/comments":
            comments.append({"body": payload["body"]})
            return {}
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["provider"] == "deepseek"
    assert result["gene"] == "Gene 003"
    assert result["workflow"] == "genesis-deepseek-agentic-solver.yml"
    assert any(
        path == "/actions/workflows/genesis-deepseek-agentic-solver.yml/dispatches"
        for _, path, _ in calls
    )


def test_capability_release_resets_prior_result_and_strategy_history():
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `blocked_protected_or_unsupported_target`"},
        {"body": "<!-- genesis-capability-dependency:88 -->\nwaiting"},
        {"body": "<!-- genesis-agentic-capability-release:88 -->\nreleased"},
    ]

    assert module.unresolved_capability_dependency(comments) is None
    assert module.latest_result_status(comments) == ""
    assert module.attempted_strategies(comments) == []
    assert module.next_strategy(comments) == "evidence_first"


def test_ready_capability_rearms_parent_even_if_waiting_label_was_manually_removed(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(
        47,
        extra_labels=("genesis-solver-exhausted",),
    )
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `blocked_protected_or_unsupported_target`"},
        {"body": "<!-- genesis-capability-dependency:88 -->\nwaiting"},
    ]
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/47/comments?per_page=100":
            release = [
                row for row in comments
                if row["body"].startswith("<!-- genesis-agentic-capability-release:")
            ]
            return comments + release
        if method == "GET" and path == "/issues/88":
            return {"number": 88, "state": "closed", "state_reason": "completed", "labels": []}
        if method == "POST" and path == "/issues/47/comments":
            comments.append({"body": payload["body"]})
            return {}
        if method == "POST" and path == "/labels":
            return {}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "dispatched"
    assert result["issue_number"] == 47
    assert result["strategy"] == "evidence_first"
    assert any(
        method == "POST"
        and path == "/issues/47/labels"
        and "genesis-autonomous" in (payload or {}).get("labels", [])
        for method, path, payload in calls
    )
    assert any(
        method == "POST"
        and path == "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches"
        for method, path, _ in calls
    )


def test_unresolved_capability_blocks_even_without_waiting_label(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []
    issue = _issue(48)
    comments = [
        {"body": "<!-- genesis-capability-dependency:99 -->\nwaiting"},
    ]
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/48/comments?per_page=100":
            return comments
        if method == "GET" and path == "/issues/99":
            return {"number": 99, "state": "open", "state_reason": None, "labels": []}
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result == {"status": "idle", "reason": "no_safely_routable_agentic_issue"}
    assert not any("/actions/workflows/" in path for _, path, _ in calls)


def test_new_material_state_epoch_ignores_stale_capability_failure():
    old = "oldstate123"
    new = "newstate456"
    comments = [
        {"body": f"<!-- genesis-anti-stuck-state:{old} -->"},
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `retry_pending_capability`"},
        {"body": f"<!-- genesis-anti-stuck-state:{new} -->\nGenesis Anti-Stuck Controller started a new attempt epoch because repository state materially changed."},
    ]
    assert module.latest_result_status(comments, new) == ""


def test_current_material_state_epoch_reads_only_fresh_result():
    token = "currentstate789"
    comments = [
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `retry_pending_capability`"},
        {"body": f"<!-- genesis-anti-stuck-state:{token} -->"},
        {"body": "<!-- genesis-agentic-strategy:diagnostic_reframe -->"},
        {"body": "<!-- genesis-agentic-strategy-result:diagnostic_reframe -->\nrepair status: `worker_failed_before_evidence`"},
    ]
    assert module.latest_result_status(comments, token) == "worker_failed_before_evidence"

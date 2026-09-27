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


def test_capability_issue_switches_provider_before_autonomous_reroute(monkeypatch):
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

    assert result["status"] == "reroute_capability"
    assert result["reason"] == "repair_failed_validation"
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


def test_recovery_engine_generation_changes_when_engine_changes(tmp_path):
    assert "scripts/agentic_strategy_repair.py" in module.RECOVERY_ENGINE_PATHS
    for relative in module.RECOVERY_ENGINE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n", encoding="utf-8")
    before = module.recovery_engine_generation(tmp_path)
    target = tmp_path / "scripts/agentic_strategy_repair.py"
    target.write_text("improved current-main satisfaction engine\n", encoding="utf-8")
    after = module.recovery_engine_generation(tmp_path)
    assert after != before


def test_recovery_material_state_token_rearms_on_repair_execution_change(tmp_path):
    for relative in set(module.RECOVERY_ENGINE_PATHS) | set(module.REPAIR_EXECUTION_PATHS):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n", encoding="utf-8")
    issue = {"body": "task", "number": 99}
    comments = []
    before = module.recovery_material_state_token(issue, "", comments, root=tmp_path)

    (tmp_path / "genesis/coding.py").write_text("new repair execution\n", encoding="utf-8")
    after_execution_change = module.recovery_material_state_token(issue, "", comments, root=tmp_path)
    assert after_execution_change != before

    (tmp_path / "genesis/coding.py").write_text("baseline\n", encoding="utf-8")
    restored = module.recovery_material_state_token(issue, "", comments, root=tmp_path)
    assert restored == before

    (tmp_path / "scripts/agentic_lab_recovery_dispatch.py").write_text(
        "controller-only change\n",
        encoding="utf-8",
    )
    after_controller_change = module.recovery_material_state_token(issue, "", comments, root=tmp_path)
    assert after_controller_change == before


def test_release_ready_capability_dependencies_preflight(monkeypatch):
    parent = _issue(817, extra_labels=(module.AGENTIC_LABEL, module.WAITING_CAPABILITY_LABEL))
    comments = [{"body": "<!-- genesis-capability-dependency:792 -->\nwaiting"}]
    released = []
    monkeypatch.setattr(module, "_all_issues", lambda repository, token: [parent])
    monkeypatch.setattr(module, "issue_comments", lambda repository, token, number: comments)
    monkeypatch.setattr(module, "capability_ready", lambda repository, token, number: number == 792)
    monkeypatch.setattr(module, "_release_waiting_issue", lambda repository, token, issue, rows, dependency: released.append((issue["number"], dependency)) or rows)
    result = module.release_ready_capability_dependencies("owner/repo", "token")
    assert result == [817]
    assert released == [(817, 792)]


def test_pause_for_capability_reuses_verified_dependency_without_waiting(monkeypatch):
    parent = _issue(817, extra_labels=(module.AGENTIC_LABEL,))
    comments = []
    monkeypatch.setattr(module, "ensure_capability_issue", lambda repository, token, issue, target, reason: {"number": 792})
    monkeypatch.setattr(module, "capability_ready", lambda repository, token, number: number == 792)
    released = []
    monkeypatch.setattr(module, "_release_waiting_issue", lambda repository, token, issue, rows, dependency: released.append((issue["number"], dependency)) or rows)
    result = module.pause_for_capability("owner/repo", "token", parent, comments, "genesis/learned_capabilities.py", "retry_pending_capability")
    assert result["status"] == "capability_already_ready"
    assert result["released"] is True
    assert released == [(817, 792)]



def test_protected_or_unsupported_target_is_routing_condition_not_capability_gap():
    assert module.capability_gap_status("blocked_protected_or_unsupported_target") is False
    assert module.capability_gap_status("retry_pending_capability") is True


def test_policy_blocked_target_is_marked_for_routing_without_capability_issue(monkeypatch):
    issue = _issue(71)
    comments = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->\nmethod"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `blocked_protected_or_unsupported_target`"},
    ]
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")
    monkeypatch.setattr(module, "ensure_anti_stuck_epoch", lambda repository, token, issue, comments, target: ("state", comments))
    monkeypatch.setattr(module, "attempt_history", lambda comments, state_token, target: [])
    monkeypatch.setattr(module, "anti_stuck_decision", lambda history: type("D", (), {"action": "capability", "reason": "strategy_set_exhausted"})())

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/71/comments?per_page=100":
            return comments
        if method == "POST" and path == "/issues/71/comments":
            comments.append({"body": payload["body"]})
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "idle"
    assert any(
        method == "POST"
        and path == "/issues/71/labels"
        and "genesis-needs-routing" in (payload or {}).get("labels", [])
        for method, path, payload in calls
    )
    assert not any(
        method == "POST" and path == "/issues" and (payload or {}).get("title", "").startswith("[Genesis Capability]")
        for method, path, payload in calls
    )



def test_epoch_migration_preserves_latest_retry_history(monkeypatch):
    issue = _issue(901)
    comments = [
        {"body": "<!-- genesis-anti-stuck-state:legacy123 -->"},
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"evidence_first\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `strategy_requires_more_methods`"},
    ]
    posted = []

    monkeypatch.setattr(module, "recovery_material_state_token", lambda issue, target, comments, root=module.ROOT: "stable456")

    def fake_request(repository, token, method, path, payload=None):
        if method == "POST" and path == "/issues/901/comments":
            posted.append(payload["body"])
            comments.append({"body": payload["body"]})
        return {}

    monkeypatch.setattr(module, "request", fake_request)
    monkeypatch.setattr(module, "issue_comments", lambda repository, token, number: list(comments))

    state_token, refreshed = module.ensure_anti_stuck_epoch(
        "owner/repo", "token", issue, comments, "genesis/example.py"
    )

    assert state_token == "legacy123"
    assert any(module.STABLE_STATE_PREFIX in body for body in posted)
    history = module.attempt_history(refreshed, state_token, "genesis/example.py")
    assert history
    assert history[-1].result == "strategy_requires_more_methods"


def test_stable_epoch_changes_only_when_material_base_changes(monkeypatch):
    issue = _issue(902)
    comments = [
        {"body": "<!-- genesis-anti-stuck-state:legacy123 -->"},
        {"body": "<!-- genesis-anti-stuck-stable-base:base-old -->"},
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `failed`"},
    ]
    posted = []
    monkeypatch.setattr(module, "recovery_material_state_token", lambda issue, target, comments, root=module.ROOT: "base-new")

    def fake_request(repository, token, method, path, payload=None):
        if method == "POST" and path == "/issues/902/comments":
            posted.append(payload["body"])
            comments.append({"body": payload["body"]})
        return {}

    monkeypatch.setattr(module, "request", fake_request)
    monkeypatch.setattr(module, "issue_comments", lambda repository, token, number: list(comments))

    state_token, _ = module.ensure_anti_stuck_epoch(
        "owner/repo", "token", issue, comments, "genesis/example.py"
    )

    assert state_token == "base-new"
    assert any("genesis-anti-stuck-state:base-new" in body for body in posted)



def test_ready_capability_release_continues_to_dispatch_in_same_pass(monkeypatch):
    issue = _issue(868, extra_labels=(module.AGENTIC_LABEL,))
    issue["body"] = "- **Target:** `genesis/workflow_governor.py`\n"
    comments = [{"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `retry_pending_capability`"}]
    calls: list[tuple[str, str, dict | None]] = []

    class Decision:
        action = "capability"
        reason = "strategy_set_exhausted"
        provider = ""
        gene = ""

    class FreshDecision:
        action = "continue"
        reason = ""
        provider = ""
        gene = ""

    decisions = iter([Decision(), FreshDecision()])

    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "issue_comments", lambda repository, token, number: list(comments))
    monkeypatch.setattr(module, "local_claim_block_reason", lambda issue, comments: "")
    monkeypatch.setattr(module, "unresolved_capability_dependency", lambda comments: None)
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")
    monkeypatch.setattr(module, "apply_integration_route", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "ensure_anti_stuck_epoch", lambda repository, token, issue, rows, target: ("fresh", list(rows)))
    monkeypatch.setattr(module, "attempt_history", lambda comments, state_token, target: [])
    monkeypatch.setattr(module, "target_attempt_history", lambda comments, target: [])
    monkeypatch.setattr(module, "anti_stuck_decision", lambda history: next(decisions))
    monkeypatch.setattr(module, "latest_result_status", lambda comments, state_token="": "retry_pending_capability" if len(calls) == 0 else "")
    monkeypatch.setattr(
        module,
        "pause_for_capability",
        lambda *args, **kwargs: {
            "status": "capability_already_ready",
            "issue_number": 868,
            "capability_issue": 951,
            "released": True,
        },
    )
    monkeypatch.setattr(module, "next_lane_strategy", lambda *args, **kwargs: "evidence_first")
    monkeypatch.setattr(module, "materially_equivalent_attempt", lambda history, candidate: False)
    monkeypatch.setattr(module, "has_state_marker", lambda comments, state_token: True)
    monkeypatch.setattr(module, "ensure_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "remove_label", lambda *args, **kwargs: None)

    def fake_request(repository, token, method, path, payload=None):
        calls.append((method, path, payload))
        return {}

    monkeypatch.setattr(module, "request", fake_request)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "dispatched"
    assert result["issue_number"] == 868
    assert any(
        method == "POST"
        and path == "/actions/workflows/genesis-agentic-strategy-worker.yml/dispatches"
        for method, path, payload in calls
    )


def test_durable_attempt_key_cannot_be_redispatched_after_duplicate_epochs(monkeypatch):
    target = "genesis/example.py"
    comments = [
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"evidence_first\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `worker_failed_before_evidence`"},
        {"body": "<!-- genesis-anti-stuck-state:same -->"},
        {"body": "<!-- genesis-anti-stuck-state:same -->"},
    ]
    history = module.target_attempt_history(comments, target)
    first = module.next_lane_strategy(
        history,
        provider="agentic-default",
        gene="Gene 0",
        target=target,
        strategies=module.STRATEGIES,
    )
    assert first == "alternative_implementation"
    duplicate = module.Attempt("evidence_first", "agentic-default", "Gene 0", target)
    assert duplicate.material_key in {attempt.material_key for attempt in history}


def test_deepseek_exhaustion_is_terminal_for_provider_epoch(monkeypatch):
    issue = _issue(905)
    target = "genesis/example.py"
    issue["body"] = f"- **Target:** `{target}`\n"
    comments = [
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"failed\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"evidence_first\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `worker_failed_before_evidence`"},
        {"body": "<!-- genesis-deepseek-epoch-exhausted:epoch123 -->\nDeepSeek exhausted."},
    ]
    calls = []
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [issue])
    monkeypatch.setattr(module, "issue_comments", lambda repository, token, number: list(comments))
    monkeypatch.setattr(module, "local_claim_block_reason", lambda issue, comments: "")
    monkeypatch.setattr(module, "unresolved_capability_dependency", lambda comments: None)
    monkeypatch.setattr(module, "safe_lane", lambda target: "generic")
    monkeypatch.setattr(module, "apply_integration_route", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "ensure_anti_stuck_epoch", lambda repository, token, issue, rows, target: ("state", list(rows)))
    monkeypatch.setattr(module, "attempt_history", lambda comments, state_token, target: ())
    monkeypatch.setattr(module, "target_attempt_history", lambda comments, target: ())
    monkeypatch.setattr(module, "latest_result_status", lambda comments, state_token="": "")
    monkeypatch.setattr(
        module,
        "anti_stuck_decision",
        lambda history: type("D", (), {"action": "switch_lane", "provider": "deepseek", "gene": "Gene 003", "reason": "rotate"})(),
    )
    monkeypatch.setattr(
        module,
        "pause_for_capability",
        lambda repository, token, issue, comments, target, reason: {"status": "waiting_capability", "reason": reason},
    )
    monkeypatch.setattr(module, "ensure_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "remove_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "request", lambda repository, token, method, path, payload=None: calls.append((method, path, payload)) or {})

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert result["status"] == "waiting_capability"
    assert result["reason"] == "deepseek_strategy_epoch_exhausted"
    assert not any("/actions/workflows/genesis-deepseek-agentic-solver.yml/dispatches" in path for _, path, _ in calls)


def test_issue_comments_paginates_retry_ledger_beyond_first_hundred(monkeypatch):
    calls = []
    first = [{"body": f"old-{index}"} for index in range(100)]
    second = [
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"alternative_implementation\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:alternative_implementation -->\nrepair status: `strategy_requires_more_methods`"},
    ]

    def fake_request(repository, token, method, path, payload=None):
        calls.append(path)
        if path == "/issues/904/comments?per_page=100":
            return first
        if path == "/issues/904/comments?per_page=100&page=2":
            return second
        raise AssertionError(path)

    monkeypatch.setattr(module, "request", fake_request)
    rows = module.issue_comments("owner/repo", "token", 904)

    assert len(rows) == 102
    assert calls == [
        "/issues/904/comments?per_page=100",
        "/issues/904/comments?per_page=100&page=2",
    ]
    history = module.target_attempt_history(rows, "genesis/example.py")
    assert history[-1].strategy == "alternative_implementation"
    assert history[-1].result == "strategy_requires_more_methods"


def test_duplicate_same_state_markers_do_not_erase_durable_strategy_history(monkeypatch):
    issue = _issue(903)
    target = "genesis/example.py"
    comments = [
        {"body": "<!-- genesis-anti-stuck-state:same123 -->\n<!-- genesis-anti-stuck-stable-base:same123 -->"},
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"evidence_first\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `strategy_requires_more_methods`"},
        {"body": "<!-- genesis-anti-stuck-state:same123 -->\n<!-- genesis-anti-stuck-stable-base:same123 -->"},
    ]
    monkeypatch.setattr(
        module,
        "recovery_material_state_token",
        lambda issue, target, comments, root=module.ROOT: "same123",
    )

    state_token, refreshed = module.ensure_anti_stuck_epoch(
        "owner/repo", "token", issue, comments, target
    )
    assert state_token == "same123"
    history = module.target_attempt_history(refreshed, target)
    assert history
    assert history[-1].strategy == "evidence_first"
    assert history[-1].result == "strategy_requires_more_methods"
    assert module.next_lane_strategy(
        history,
        provider="agentic-default",
        gene="Gene 0",
        target=target,
        strategies=module.STRATEGIES,
    ) == "alternative_implementation"


def test_cross_epoch_more_methods_keeps_lane_for_next_strategy(monkeypatch):
    issue = _issue(77)
    comments = [
        {"body": "<!-- genesis-anti-stuck-attempt:{\"blocker\":\"\",\"gene\":\"Gene 0\",\"provider\":\"agentic-default\",\"strategy\":\"evidence_first\",\"target\":\"genesis/example.py\"} -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first -->\nrepair status: `strategy_requires_more_methods`"},
    ]
    history = module.target_attempt_history(comments, "genesis/example.py")
    decision = module.anti_stuck_decision(history)
    assert decision.action == "continue"
    assert decision.reason == "same_lane_methods_remain"



def test_live_priority_order_prefers_shared_capability_blocker(monkeypatch):
    capability = _issue(200, body="<!-- genesis-capability-work:abc -->")
    normal = _issue(100)
    monkeypatch.setattr(
        module,
        "issue_comments",
        lambda repository, token, number: (
            [
                {"body": "<!-- genesis-capability-parent:10 -->"},
                {"body": "<!-- genesis-capability-parent:11 -->"},
            ]
            if number == 200
            else []
        ),
    )

    ordered = module._live_priority_order("owner/repo", "token", [normal, capability])

    assert [issue["number"] for issue in ordered] == [200, 100]


def test_reserve_releases_ready_capability_parents_before_selection(monkeypatch):
    calls = []
    monkeypatch.setattr(
        module,
        "release_ready_capability_dependencies",
        lambda repository, token: calls.append("release") or [],
    )
    monkeypatch.setattr(module, "open_agentic_issues", lambda repository, token: [])
    monkeypatch.setattr(module, "_live_priority_order", lambda repository, token, issues: issues)

    result = module.reserve_and_dispatch("owner/repo", "token")

    assert calls == ["release"]
    assert result["status"] == "idle"

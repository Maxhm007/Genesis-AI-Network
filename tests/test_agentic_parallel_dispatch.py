from datetime import datetime, timezone

import pytest

import scripts.agentic_parallel_dispatch as module


@pytest.fixture(autouse=True)
def restore_dispatch_bindings(monkeypatch):
    # main() configures the standalone controller; keep those bindings local
    # to each test when several controller modules share one Python process.
    for attribute in ("issue_comments", "open_agentic_issues", "next_strategy"):
        monkeypatch.setattr(module.agentic, attribute, getattr(module.agentic, attribute))


def _issue(number: int, created_at: str, *, labels=(), body=""):
    return {
        "number": number,
        "created_at": created_at,
        "body": body,
        "labels": [{"name": label} for label in labels],
    }


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending", "requested"])
@pytest.mark.parametrize("workflow", [
    "genesis-agentic-strategy-worker.yml",
    "genesis-deepseek-agentic-solver.yml",
    "genesis-bounded-repair-worker.yml",
])
def test_live_worker_with_dynamic_run_name_prevents_reservation_reclaim(monkeypatch, status, workflow):
    def request(repository, token, method, path, *args):
        return {"workflow_runs": [{
            "name": "Issue #867 — evidence_first",
            "event": "workflow_dispatch",
            "path": f".github/workflows/{workflow}@refs/heads/main",
        }]} if f"status={status}&" in path else {"workflow_runs": []}

    monkeypatch.setattr(module.agentic, "request", request)
    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: pytest.fail("live worker must keep its reservation"))
    assert module._live_agentic_worker_exists("owner/repo", "token")
    assert module._reclaim_stale_sequential_reservation("owner/repo", "token") == []


def test_unrelated_live_workflow_does_not_block_recovery(monkeypatch):
    monkeypatch.setattr(module.agentic, "request", lambda *args: {"workflow_runs": [{
        "name": "Genesis Agentic Lab Recovery",
        "event": "workflow_dispatch",
        "path": ".github/workflows/genesis-agentic-lab-recovery.yml",
    }]})
    assert not module._live_agentic_worker_exists("owner/repo", "token")


def test_push_baseline_validation_does_not_block_recovery(monkeypatch):
    monkeypatch.setattr(module.agentic, "request", lambda *args: {"workflow_runs": [{
        "name": "Issue #validation — push",
        "event": "push",
        "path": ".github/workflows/genesis-agentic-strategy-worker.yml",
    }]})
    assert not module._live_agentic_worker_exists("owner/repo", "token")


def test_legacy_dispatched_worker_name_keeps_reservation(monkeypatch):
    monkeypatch.setattr(module.agentic, "request", lambda *args: {"workflow_runs": [{
        "name": "Genesis DeepSeek Agentic Solver",
        "event": "workflow_dispatch",
    }]})
    assert module._live_agentic_worker_exists("owner/repo", "token")


def test_actions_visibility_failure_keeps_worker_reservation(monkeypatch):
    def unavailable(*args):
        raise RuntimeError("Actions unavailable")

    monkeypatch.setattr(module.agentic, "request", unavailable)
    assert module._live_agentic_worker_exists("owner/repo", "token")


def test_dependency_unlock_count_tracks_shared_capability_parent_links():
    issues = [
        _issue(100, "2026-09-20T00:00:00Z"),
        _issue(101, "2026-09-20T01:00:00Z"),
        _issue(200, "2026-09-20T02:00:00Z", labels=("genesis-capability-gap",)),
    ]
    comments = {
        100: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
        101: [{"body": "<!-- genesis-capability-dependency:200 -->"}],
        200: [],
    }

    assert module._dependency_unlock_counts(issues, comments) == {200: 2}


def test_value_score_rewards_shared_capability_unlocks():
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    capability = _issue(
        200,
        "2026-09-20T00:00:00Z",
        labels=("genesis-capability-gap",),
        body="<!-- genesis-capability-work:abc -->",
    )
    ordinary = _issue(201, "2026-09-20T00:00:00Z")

    cap = module._score_issue(capability, [], unlock_count=4, now=now)
    normal = module._score_issue(ordinary, [], unlock_count=0, now=now)

    assert cap["score"] > normal["score"]
    assert cap["breakdown"]["blocked_issues"] > 0


def test_age_component_prevents_old_work_from_permanent_starvation():
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    old = _issue(1, "2026-08-01T00:00:00Z")
    fresh = _issue(2, "2026-09-24T23:00:00Z")

    old_score = module._score_issue(old, [], unlock_count=0, now=now)
    fresh_score = module._score_issue(fresh, [], unlock_count=0, now=now)

    assert old_score["breakdown"]["age"] > fresh_score["breakdown"]["age"]


def test_main_decomposes_targetless_work_before_parallel_dispatch(monkeypatch):
    issue = _issue(
        857,
        "2026-09-18T00:00:00Z",
        labels=("genesis-autonomous", "genesis-architecture-route"),
        body="Architecture work without an explicit target",
    )
    events: list[str] = []
    reads = {"count": 0}

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def open_issues(repository, token):
        reads["count"] += 1
        return [issue]

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", open_issues)
    monkeypatch.setattr(module.policy, "_restore_agentic_visibility", lambda *args: [])
    monkeypatch.setattr(module.agentic, "release_ready_capability_dependencies", lambda *args: [])
    def decompose_once(repository, token, issues):
        events.append("decompose")
        if len(events) == 1:
            return {
                "status": "decomposed",
                "issue_number": 857,
                "target": "scripts/capability_issue_priority_dispatch.py",
            }
        return {"status": "idle", "reason": "no_more_targetless_work"}

    monkeypatch.setattr(module.policy, "_decompose_oldest_issue", decompose_once)
    monkeypatch.setattr(module, "_active_issue_numbers", lambda *args: [])
    monkeypatch.setattr(module, "_parallel_routable_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        module.agentic,
        "reserve_and_dispatch",
        lambda *args: {"status": "idle", "reason": "test"},
    )

    assert module.main() == 0
    assert events == ["decompose", "decompose"]
    assert reads["count"] >= 2



def test_exhausted_backlog_is_ranked_before_fresh_higher_value_work(monkeypatch):
    exhausted = _issue(
        10,
        "2026-09-20T00:00:00Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-solver-exhausted"),
        body="- **Target:** `genesis/example.py`",
    )
    fresh = _issue(
        11,
        "2026-09-25T00:00:00Z",
        labels=("genesis-autonomous", "agentic-lab", "owner-priority"),
        body="- **Target:** `genesis/example.py`",
    )

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [fresh, exhausted])
    monkeypatch.setattr(module.policy, "_all_issue_comments", lambda *args: [])
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module.policy, "_infra_quarantined", lambda *args: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: "generic")

    ordered = module._parallel_routable_issues("owner/repo", "token")
    assert [row["number"] for row in ordered[:2]] == [10, 11]



def test_capability_dependency_is_ranked_before_exhausted_parent(monkeypatch):
    capability = _issue(
        951,
        "2026-09-26T16:09:40Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-capability-gap"),
        body="<!-- genesis-capability-work:abc -->\n- **Target:** `genesis/github_issue_capability_builder.py`",
    )
    exhausted = _issue(
        857,
        "2026-09-18T00:00:00Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-solver-exhausted"),
        body="- **Target:** `scripts/capability_issue_priority_dispatch.py`",
    )
    parent = _issue(
        863,
        "2026-09-18T01:00:00Z",
        labels=("genesis-autonomous", "agentic-lab"),
        body="blocked parent",
    )
    comments = {
        951: [],
        857: [],
        863: [{"body": "<!-- genesis-capability-dependency:951 -->"}],
    }

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [exhausted, parent, capability])
    monkeypatch.setattr(module.policy, "_all_issue_comments", lambda repository, token, number: comments[number])
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: issue["number"] != 863)
    monkeypatch.setattr(module.policy, "_infra_quarantined", lambda *args: False)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: "generic")

    ordered = module._parallel_routable_issues("owner/repo", "token")
    assert [row["number"] for row in ordered[:2]] == [951, 857]


def test_recovery_lane_is_reserved_and_selected_first(monkeypatch):
    active_dev = _issue(
        10,
        "2026-09-20T00:00:00Z",
        labels=("genesis-autonomous", "genesis-repair-in-progress"),
        body="- **Target:** `genesis/active.py`",
    )
    recovery = _issue(
        11,
        "2026-09-20T01:00:00Z",
        labels=("genesis-autonomous", "genesis-solver-exhausted"),
        body="- **Target:** `genesis/recovery.py`",
    )
    development = _issue(
        12,
        "2026-09-20T02:00:00Z",
        labels=("genesis-autonomous",),
        body="- **Target:** `genesis/development.py`",
    )
    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [active_dev, recovery, development])
    monkeypatch.setattr(module, "_parallel_routable_issues", lambda *args, **kwargs: [development, recovery])
    selected = module._lane_routable_issues("owner/repo", "token")
    assert [row["number"] for row in selected] == [11, 12]


def test_parallel_lane_skips_active_target_collision(monkeypatch):
    active_recovery = _issue(
        20,
        "2026-09-20T00:00:00Z",
        labels=("genesis-autonomous", "genesis-repair-in-progress", "genesis-solver-exhausted"),
        body="- **Target:** `genesis/recovery.py`",
    )
    active_dev = _issue(
        21,
        "2026-09-20T01:00:00Z",
        labels=("genesis-autonomous", "genesis-repair-in-progress"),
        body="- **Target:** `genesis/shared.py`",
    )
    collision = _issue(
        22,
        "2026-09-20T02:00:00Z",
        labels=("genesis-autonomous",),
        body="- **Target:** `genesis/shared.py`",
    )
    independent = _issue(
        23,
        "2026-09-20T03:00:00Z",
        labels=("genesis-autonomous",),
        body="- **Target:** `genesis/independent.py`",
    )
    monkeypatch.setattr(
        module.policy,
        "_all_open_issues_fifo",
        lambda *args: [active_recovery, active_dev, collision, independent],
    )
    monkeypatch.setattr(module, "_parallel_routable_issues", lambda *args, **kwargs: [collision, independent])
    selected = module._lane_routable_issues("owner/repo", "token")
    assert [row["number"] for row in selected] == [23]


def test_main_refills_six_bounded_lanes(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [])
    monkeypatch.setattr(module.policy, "_restore_agentic_visibility", lambda *args: [])
    monkeypatch.setattr(module.policy, "_terminalize_non_actionable_issues", lambda *args: [])
    monkeypatch.setattr(module.agentic, "release_ready_capability_dependencies", lambda *args: [])
    monkeypatch.setattr(module.policy, "_decompose_oldest_issue", lambda *args: {"status": "idle"})
    monkeypatch.setattr(module, "_active_issue_numbers", lambda *args: [])

    dispatched = []
    def dispatch(*args):
        number = 100 + len(dispatched)
        dispatched.append(number)
        return {"status": "dispatched", "issue_number": number}

    monkeypatch.setattr(module.agentic, "reserve_and_dispatch", dispatch)
    assert module.main() == 0
    assert dispatched == [100, 101, 102, 103, 104, 105]
    assert module.MAX_PARALLEL == 6
    assert module.DEVELOPMENT_SLOTS == 4
    assert module.RECOVERY_SLOTS == 2


def test_legacy_sequential_entrypoint_uses_parallel_lane_selector(monkeypatch):
    expected = [_issue(31, "2026-09-20T00:00:00Z")]
    monkeypatch.setattr(module, "_lane_routable_issues", lambda *args: expected)
    assert module._sequential_routable_issues("owner/repo", "token") == expected


def test_main_skips_noop_candidate_and_continues_filling_lanes(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    candidates = [
        _issue(867, "2026-09-18T00:00:00Z", body="- **Target:** `genesis/health.py`"),
        _issue(992, "2026-09-29T00:00:00Z", body="- **Target:** `genesis/learned_capabilities.py`"),
        _issue(874, "2026-09-18T01:00:00Z", body="- **Target:** `genesis/capability_routing.py`"),
    ]

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: candidates)
    monkeypatch.setattr(module.policy, "_restore_agentic_visibility", lambda *args: [])
    monkeypatch.setattr(module.policy, "_terminalize_non_actionable_issues", lambda *args: [])
    monkeypatch.setattr(module.agentic, "release_ready_capability_dependencies", lambda *args: [])
    monkeypatch.setattr(module.policy, "_decompose_oldest_issue", lambda *args: {"status": "idle"})
    monkeypatch.setattr(module, "_active_issue_numbers", lambda *args: [])
    monkeypatch.setattr(module, "_parallel_routable_issues", lambda *args, **kwargs: candidates)

    seen = []
    def dispatch(repo, token):
        available = module.agentic.open_agentic_issues(repo, token)
        number = available[0]["number"] if available else 0
        seen.append(number)
        if number == 867:
            return {
                "status": "capability_escalation_already_ready",
                "issue_number": 867,
                "reason": "retry_pending_capability",
            }
        if number:
            return {"status": "dispatched", "issue_number": number}
        return {"status": "idle", "reason": "no_safely_routable_agentic_issue"}

    monkeypatch.setattr(module.agentic, "reserve_and_dispatch", dispatch)
    assert module.main() == 0
    assert seen[:3] == [867, 992, 874]


def test_visibility_restore_does_not_scan_comments_for_already_visible_issue(monkeypatch):
    issue = _issue(
        867,
        "2026-09-20T00:00:00Z",
        labels=("agentic-lab", "genesis-autonomous"),
    )

    monkeypatch.setattr(
        module.policy,
        "_infra_quarantined",
        lambda *args: pytest.fail("already-visible issue must not fetch quarantine comments"),
    )
    monkeypatch.setattr(
        module.agentic,
        "request",
        lambda *args, **kwargs: pytest.fail("already-visible issue must not write GitHub state"),
    )

    assert module.policy._restore_agentic_visibility("owner/repo", "token", [issue]) == []


def test_visibility_restore_checks_quarantine_only_when_repair_is_needed(monkeypatch):
    issue = _issue(
        868,
        "2026-09-20T00:00:00Z",
        labels=("genesis-autonomous",),
    )
    checked = []

    def quarantined(repository, token, number):
        checked.append(number)
        return True

    monkeypatch.setattr(module.policy, "_infra_quarantined", quarantined)
    monkeypatch.setattr(
        module.agentic,
        "request",
        lambda *args, **kwargs: pytest.fail("quarantined issue must not be relabeled"),
    )

    assert module.policy._restore_agentic_visibility("owner/repo", "token", [issue]) == []
    assert checked == [868]


def test_kernel_ready_issue_is_dispatchable(monkeypatch):
    ready = _issue(
        1108,
        "2026-10-24T20:30:17Z",
        labels=("genesis-autonomous", "agentic-lab"),
        body="- **Target:** `genesis/example.py`",
    )
    ready["updated_at"] = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [ready])
    monkeypatch.setattr(module.policy, "_all_issue_comments", lambda *args: [])
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: "generic")

    selected = module._parallel_routable_issues("owner/repo", "token")
    assert [row["number"] for row in selected] == [1108]


def test_kernel_excludes_validating_and_verified_from_fresh_dispatch(monkeypatch):
    validating = _issue(
        1110,
        "2026-10-24T20:30:17Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-validating"),
        body="- **Target:** `genesis/validation.py`",
    )
    verified = _issue(
        1111,
        "2026-10-24T20:30:17Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-verified"),
        body="- **Target:** `genesis/closure.py`",
    )
    for issue in (validating, verified):
        issue["updated_at"] = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [validating, verified])
    monkeypatch.setattr(module.policy, "_all_issue_comments", lambda *args: [])
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: "generic")

    assert module._parallel_routable_issues("owner/repo", "token") == []


def test_kernel_stalled_ready_issue_enters_recovery_lane(monkeypatch):
    stalled = _issue(
        1112,
        "2026-10-20T00:00:00Z",
        labels=("genesis-autonomous", "agentic-lab"),
        body="- **Target:** `genesis/failure_memory.py`",
    )
    stalled["updated_at"] = "2026-10-20T00:00:00Z"

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [stalled])
    monkeypatch.setattr(module, "_parallel_routable_issues", lambda *args, **kwargs: [stalled])

    selected = module._lane_routable_issues("owner/repo", "token")
    assert [row["number"] for row in selected] == [1112]
    assert module._is_recovery_issue(stalled) is True


def test_kernel_blocked_issue_enters_recovery_even_when_recent():
    blocked = _issue(
        1113,
        "2026-10-24T20:30:17Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-blocked"),
        body="- **Target:** `genesis/metrics.py`",
    )
    blocked["updated_at"] = datetime.now(timezone.utc).isoformat()
    assert module._is_recovery_issue(blocked) is True


def test_kernel_targetless_recovery_is_prioritized_for_decomposition(monkeypatch):
    ordinary = _issue(
        1100,
        "2026-10-24T18:00:00Z",
        labels=("genesis-autonomous",),
        body="Monitoring task without a target",
    )
    recovery = _issue(
        1109,
        "2026-10-24T20:30:19Z",
        labels=("genesis-autonomous", "agentic-lab"),
        body="Recovery task without a target",
    )
    ordinary["updated_at"] = "2026-10-20T00:00:00Z"
    recovery["updated_at"] = "2026-10-20T00:00:00Z"

    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target))

    ordered = module._kernel_decomposition_order([ordinary, recovery])
    assert [row["number"] for row in ordered[:2]] == [1109, 1100]


def test_kernel_targetless_validating_issue_is_not_prioritized(monkeypatch):
    validating = _issue(
        1110,
        "2026-10-24T20:30:21Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-validating"),
        body="Validation work without target",
    )
    ready = _issue(
        1111,
        "2026-10-24T20:30:22Z",
        labels=("genesis-autonomous", "agentic-lab"),
        body="Ready work without target",
    )
    validating["updated_at"] = datetime.now(timezone.utc).isoformat()
    ready["updated_at"] = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module.agentic, "safe_lane", lambda target: bool(target))

    ordered = module._kernel_decomposition_order([validating, ready])
    assert ordered[0]["number"] == 1111

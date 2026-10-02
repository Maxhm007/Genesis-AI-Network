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


def test_sequential_focus_executes_unresolved_capability_dependency(monkeypatch):
    parent = _issue(
        857,
        "2026-09-18T00:00:00Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-sequential-focus", "genesis-waiting-capability"),
        body="- **Target:** `scripts/capability_issue_priority_dispatch.py`",
    )
    capability = _issue(
        973,
        "2026-09-27T15:42:00Z",
        labels=("genesis-autonomous", "agentic-lab", "genesis-capability-gap"),
        body="<!-- genesis-capability-work:abc -->\n- **Target:** `genesis/github_issue_capability_builder.py`",
    )

    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [parent, capability])
    monkeypatch.setattr(
        module.policy,
        "_all_issue_comments",
        lambda repository, token, number: (
            [{"body": "<!-- genesis-capability-dependency:973 -->"}] if number == 857 else []
        ),
    )
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)

    selected = module._sequential_routable_issues("owner/repo", "token")

    assert [row["number"] for row in selected] == [973]
    assert "genesis-sequential-focus" in {row["name"] for row in parent["labels"]}
    assert "genesis-sequential-focus" not in {row["name"] for row in capability["labels"]}


def test_focused_dependency_routing_is_serviced_before_dispatch(monkeypatch):
    parent = _issue(867, "2026-09-18T00:00:00Z", labels=(
        "genesis-autonomous", "agentic-lab", "genesis-sequential-focus", "genesis-waiting-capability"))
    dependency = _issue(1022, "2026-09-29T00:00:00Z", labels=(
        "genesis-autonomous", "agentic-lab", "genesis-needs-routing"),
        body="<!-- genesis-capability-work:abc -->\n- **Target:** `genesis/github_issue_capability_builder.py`")
    unrelated = _issue(868, "2026-09-18T01:00:00Z")
    events = []
    for attribute in ("issue_comments", "open_agentic_issues", "next_strategy"):
        monkeypatch.setattr(module.agentic, attribute, getattr(module.agentic, attribute))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(module.policy, "_all_open_issues_fifo", lambda *args: [parent, unrelated, dependency])
    monkeypatch.setattr(module.policy, "_all_issue_comments", lambda repo, token, number:
                        [{"body": "<!-- genesis-capability-dependency:1022 -->"}] if number == 867 else [])
    monkeypatch.setattr(module.policy, "_actionable", lambda issue: True)
    monkeypatch.setattr(module, "_live_agentic_worker_exists", lambda *args: False)
    monkeypatch.setattr(module, "_reclaim_stale_sequential_reservation", lambda *args: [])
    monkeypatch.setattr(module, "_active_issue_numbers", lambda *args: [])

    def route(repo, token, issues):
        assert [i["number"] for i in issues] == [1022]
        events.append("route")
        return {"status": "routing_released", "issue_number": 1022}

    def dispatch(*args):
        assert events == ["route"]
        events.append("dispatch")
        return {"status": "dispatched", "issue_number": 1022}

    monkeypatch.setattr(module.policy, "_decompose_oldest_issue", route)
    monkeypatch.setattr(module.agentic, "reserve_and_dispatch", dispatch)
    assert module.main() == 0
    assert events == ["route", "dispatch"]
    assert "genesis-sequential-focus" in module.agentic.labels(parent)


def test_focused_legacy_architecture_plan_is_repaired_before_dispatch(monkeypatch):
    owned = _issue(867, '2026-09-18T00:00:00Z', labels=('genesis-autonomous', 'agentic-lab', 'genesis-sequential-focus'), body='- **Target:** `genesis/architecture_extensions/legacy.py`')
    calls = []
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    monkeypatch.setenv('GITHUB_TOKEN', 'token')
    monkeypatch.setattr(module.policy, '_all_open_issues_fifo', lambda *args: [owned])
    monkeypatch.setattr(module.policy, '_all_issue_comments', lambda *args: [])
    monkeypatch.setattr(module, '_sequential_routable_issues', lambda *args: [owned])
    monkeypatch.setattr(module.agentic, 'safe_lane', lambda *args: 'generic')
    monkeypatch.setattr(module, '_live_agentic_worker_exists', lambda *args: False)
    monkeypatch.setattr(module, '_reclaim_stale_sequential_reservation', lambda *args: calls.append(('reclaim', 867)) or [867])
    monkeypatch.setattr(module, '_active_issue_numbers', lambda *args: [])
    monkeypatch.setattr(module.policy, '_decompose_oldest_issue', lambda repo, token, issues: calls.append(('plan', issues[0]['number'])) or {'status': 'retargeted'})
    monkeypatch.setattr(module.agentic, 'reserve_and_dispatch', lambda *args: calls.append(('dispatch', 867)) or {'status': 'dispatched', 'issue_number': 867})
    assert module.main() == 0
    assert calls == [('reclaim', 867), ('plan', 867), ('dispatch', 867)]

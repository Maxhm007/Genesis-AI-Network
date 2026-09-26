from datetime import datetime, timezone

import scripts.agentic_parallel_dispatch as module


def _issue(number: int, created_at: str, *, labels=(), body=""):
    return {
        "number": number,
        "created_at": created_at,
        "body": body,
        "labels": [{"name": label} for label in labels],
    }


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
    monkeypatch.setattr(
        module.policy,
        "_decompose_oldest_issue",
        lambda repository, token, issues: events.append("decompose") or {
            "status": "decomposed",
            "issue_number": 857,
            "target": "scripts/capability_issue_priority_dispatch.py",
        },
    )
    monkeypatch.setattr(module, "_active_issue_numbers", lambda *args: [])
    monkeypatch.setattr(
        module.agentic,
        "reserve_and_dispatch",
        lambda *args: {"status": "idle", "reason": "test"},
    )

    assert module.main() == 0
    assert events == ["decompose"]
    assert reads["count"] >= 2

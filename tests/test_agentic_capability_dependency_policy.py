from pathlib import Path

from scripts import agentic_lab_recovery_dispatch as dispatcher


DISPATCHER = Path("scripts/agentic_lab_recovery_dispatch.py")


def test_capability_gap_keeps_parent_open_and_paused() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")
    pause_section = text.split("def pause_for_capability(", 1)[1].split("\ndef _release_waiting_issue(", 1)[0]

    assert "genesis-waiting-capability" in text
    assert "Parent Issue" in text
    assert "stays open but is paused" in pause_section
    assert "state_reason" not in pause_section
    assert '"state": "closed"' not in pause_section


def test_capability_work_does_not_create_unbounded_dependency_chain() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "genesis-needs-human" in text
    assert "will not create an unbounded chain of capability Issues" in text


def test_capability_completion_releases_parent_for_fresh_strategy_cycle() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "genesis-agentic-capability-release" in text
    assert "fresh Agentic Lab strategy cycle" in text


def test_capability_identity_is_shared_by_target_and_blocker_class() -> None:
    coding = dispatcher._capability_fingerprint("genesis/coding.py", "retry_pending_capability")
    coding_same = dispatcher._capability_fingerprint("genesis/coding.py", "RETRY_PENDING_CAPABILITY")
    benchmark = dispatcher._capability_fingerprint("genesis/benchmark_execution.py", "retry_pending_capability")
    different_reason = dispatcher._capability_fingerprint("genesis/coding.py", "blocked_no_safe_context")

    assert coding == coding_same
    assert coding != benchmark
    assert coding != different_reason


def test_legacy_capability_issue_is_reused_for_same_target_and_blocker(monkeypatch) -> None:
    existing = {
        "number": 781,
        "body": (
            "<!-- genesis-capability-work:legacy -->\n"
            "<!-- genesis-capability-parent:709 -->\n"
            "- **Blocked target:** `genesis/coding.py`\n"
            "- **Observed blocker:** `retry_pending_capability`\n"
            "- **Task type:** `capability_growth`\n"
            "- **Target:** `genesis/github_issue_capability_builder.py`\n"
        ),
    }
    monkeypatch.setattr(dispatcher, "_all_issues", lambda repository, token: [existing])

    def unexpected_request(*args, **kwargs):
        raise AssertionError("matching shared capability must be reused instead of creating another Issue")

    monkeypatch.setattr(dispatcher, "request", unexpected_request)

    reused = dispatcher.ensure_capability_issue(
        "owner/repo",
        "token",
        {"number": 999},
        "genesis/coding.py",
        "retry_pending_capability",
    )

    assert reused is existing


def test_capability_parent_links_remain_independent() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert "genesis-capability-parent:" in text
    assert "Each linked parent remains open but paused" in text
    assert "independently resume every linked parent" in text

from pathlib import Path


DISPATCHER = Path("scripts/agentic_lab_recovery_dispatch.py")


def test_capability_gap_keeps_parent_open_and_paused() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")
    pause_section = text.split("def pause_for_capability(", 1)[1].split("\ndef _release_waiting_issue(", 1)[0]

    assert "genesis-waiting-capability" in pause_section
    assert "Parent Issue" in pause_section
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

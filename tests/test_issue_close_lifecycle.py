from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEAL = ROOT / ".github/workflows/genesis-closed-issue-seal.yml"
BOUNDED = ROOT / ".github/workflows/genesis-bounded-repair-worker.yml"
SPECIALIST = ROOT / ".github/workflows/genesis-specialist-repair-worker.yml"
CONTROLLER = ROOT / ".github/workflows/genesis-sequential-issue-controller.yml"


def test_global_closure_guard_requires_verification_for_bot_closure() -> None:
    text = SEAL.read_text(encoding="utf-8")
    assert "github.event.action == 'closed'" in text
    assert "ACTOR: ${{ github.actor }}" in text
    assert "genesis-verified" in text
    assert "Genesis closure guard rejected this automatic close" in text
    assert "--method PATCH -f state=open" in text


def test_verified_bot_closure_is_sealed() -> None:
    text = SEAL.read_text(encoding="utf-8")
    assert "genesis-closed-sealed-completed" in text
    assert "Accepted verified automatic closure" in text


def test_failed_workers_keep_issue_open_for_retry() -> None:
    bounded = BOUNDED.read_text(encoding="utf-8")
    specialist = SPECIALIST.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")

    bounded_release = bounded[bounded.index("Release unsuccessful reservation safely"):]
    specialist_release = specialist[specialist.index("Release unsuccessful reservation with bounded terminal policy"):]
    controller_retry = controller[controller.index("mark_retry_or_blocked()") : controller.index("ensure_label genesis-claimed")]

    assert "state=closed -f state_reason=not_planned" not in bounded_release
    assert "state=closed -f state_reason=not_planned" not in specialist_release
    assert "state=closed -f state_reason=not_planned" not in controller_retry
    assert "Issue remains OPEN" in bounded_release
    assert "Issue remains open" in specialist_release
    assert "State: **OPEN; escalated" in controller_retry


def test_successful_workers_verify_then_close() -> None:
    bounded = BOUNDED.read_text(encoding="utf-8")
    specialist = SPECIALIST.read_text(encoding="utf-8")

    for text in (bounded, specialist):
        verified_at = text.index("genesis-verified")
        close_at = text.index("state=closed", verified_at)
        assert verified_at < close_at

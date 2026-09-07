from pathlib import Path


WORKER = Path(".github/workflows/genesis-agentic-strategy-worker.yml")


def test_agentic_strategy_worker_never_closes_failed_issue() -> None:
    text = WORKER.read_text(encoding="utf-8")
    release = text[text.index("Release unsuccessful Agentic reservation without closing Issue") :]

    assert "The Issue remains open" in release
    assert "--add-label agentic-lab --add-label genesis-solver-exhausted" in release
    assert "state=closed -f state_reason=not_planned" not in release


def test_agentic_strategy_worker_only_closes_after_verified_promotion() -> None:
    text = WORKER.read_text(encoding="utf-8")
    promotion = text[text.index("Independently validate and promote exact Agentic candidate") : text.index("Release unsuccessful Agentic reservation without closing Issue")]

    assert "python -m pytest -q" in promotion
    assert "genesis-verified" in promotion
    assert "state=closed -f state_reason=completed" in promotion


def test_agentic_strategy_worker_uses_explicit_strategy_input() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "--strategy \"$STRATEGY\"" in text
    assert "evidence_first" in text
    assert "alternative_implementation" in text
    assert "diagnostic_reframe" in text
    assert "dependency_diagnosis" in text

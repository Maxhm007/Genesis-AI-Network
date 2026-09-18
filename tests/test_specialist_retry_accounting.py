from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALIST_WORKER = ROOT / ".github/workflows/genesis-specialist-repair-worker-v2.yml"


def test_specialist_retry_state_is_durable_and_bounded() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert "genesis-specialist-repair-attempt-[123]" in worker
    release_at = worker.index("Release unsuccessful reservation without false closure")
    assert "state=closed -f state_reason=not_planned" not in worker[release_at:]


def test_successful_specialist_repair_clears_attempt_state() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert "genesis-specialist-repair-attempt-1" in worker
    assert "genesis-specialist-repair-attempt-2" in worker
    assert "genesis-specialist-repair-attempt-3" in worker
    assert "genesis-verified" in worker

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALIST_WORKER = ROOT / ".github/workflows/genesis-specialist-repair-worker.yml"


def test_specialist_retry_state_is_durable_and_bounded() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert "genesis-specialist-repair-attempt-[123]" in worker
    assert "genesis-repair-attempt-[123]" in worker
    assert 'effective_attempt="${ATTEMPT:-}"' in worker
    assert 'status="${status}:attempt_recording_failed"' in worker
    assert 'if [[ "$effective_attempt" -ge 3' in worker
    assert "state=closed -f state_reason=not_planned" in worker
    assert "${ATTEMPT:-1}" not in worker


def test_specialist_attempt_comment_uses_a_real_newline() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert "printf -v attempt_comment" in worker
    assert "genesis-specialist-repair-attempt:%s" in worker
    assert "--body \"$attempt_comment\"" in worker


def test_successful_specialist_repair_clears_attempt_state() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert "genesis-specialist-repair-attempt-1" in worker
    assert "genesis-specialist-repair-attempt-2" in worker
    assert "genesis-specialist-repair-attempt-3" in worker
    assert "genesis-verified" in worker

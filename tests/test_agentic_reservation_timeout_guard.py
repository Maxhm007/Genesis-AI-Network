from pathlib import Path
import re


AGENTIC_WORKER = Path(".github/workflows/genesis-agentic-strategy-worker.yml")
AGENTIC_DISPATCH = Path("scripts/agentic_lab_capability_first_dispatch.py")


def _required_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, f"missing required timeout setting: {pattern}"
    return int(match.group(1))


def test_stale_reservation_threshold_exceeds_agentic_worker_timeout():
    worker_text = AGENTIC_WORKER.read_text(encoding="utf-8")
    dispatch_text = AGENTIC_DISPATCH.read_text(encoding="utf-8")
    worker_timeout = _required_int(worker_text, r"^\s*timeout-minutes:\s*(\d+)\s*$")
    dispatch_stale = _required_int(dispatch_text, r"^STALE_RESERVATION_MINUTES\s*=\s*(\d+)\s*$")
    assert worker_timeout == 120
    assert dispatch_stale > worker_timeout
    assert dispatch_stale >= 135

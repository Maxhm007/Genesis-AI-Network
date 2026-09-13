from pathlib import Path
import re


AGENTIC_WORKER = Path('.github/workflows/genesis-agentic-strategy-worker.yml')
SEQUENTIAL_CONTROLLER = Path('.github/workflows/genesis-sequential-issue-controller.yml')
AGENTIC_DISPATCH = Path('scripts/agentic_lab_capability_first_dispatch.py')


def _required_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, f'missing required timeout setting: {pattern}'
    return int(match.group(1))


def test_stale_reservation_thresholds_exceed_agentic_worker_timeout():
    worker_text = AGENTIC_WORKER.read_text(encoding='utf-8')
    controller_text = SEQUENTIAL_CONTROLLER.read_text(encoding='utf-8')
    dispatch_text = AGENTIC_DISPATCH.read_text(encoding='utf-8')

    worker_timeout = _required_int(worker_text, r'^\s*timeout-minutes:\s*(\d+)\s*$')
    controller_stale = _required_int(controller_text, r'^\s*stale_minutes=(\d+)\s*$')
    dispatch_stale = _required_int(dispatch_text, r'^STALE_RESERVATION_MINUTES\s*=\s*(\d+)\s*$')

    # A reservation aged 100-120 minutes must still be valid because the
    # Agentic worker itself is allowed to run for 120 minutes.
    assert worker_timeout == 120
    assert controller_stale > worker_timeout
    assert dispatch_stale > worker_timeout
    assert controller_stale >= 135
    assert dispatch_stale >= 135

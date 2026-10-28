from pathlib import Path
import ast


def test_disabled_worker_dispatch_does_not_exhaust_issue():
    source = Path("scripts/agentic_lab_recovery_dispatch.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert '"status": "dispatch_unavailable"' in source
    assert "genesis-agentic-dispatch-unavailable" in source
    block = source.split("                # A disabled worker or transport failure")[1].split("\n        result = {", 1)[0]
    assert 'EXHAUSTED_LABEL' not in block
    assert 'remove_label(repository, token, number, "genesis-repair-in-progress")' in block

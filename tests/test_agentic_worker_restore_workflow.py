from pathlib import Path


def test_agentic_controller_can_restore_disabled_canonical_worker():
    workflow = Path(".github/workflows/genesis-agentic-lab-recovery.yml").read_text(encoding="utf-8")
    assert "Restore canonical Agentic Strategy Worker if disabled" in workflow
    assert 'state" == "disabled_manually"' in workflow
    assert 'state" == "disabled_inactivity"' in workflow
    assert '/actions/workflows/$workflow/enable' in workflow
    assert workflow.index("Restore canonical Agentic Strategy Worker if disabled") < workflow.index("Dispatch bounded parallel Agentic lanes")
    assert 'state" != "active"' in workflow

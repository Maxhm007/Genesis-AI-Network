"""Guard regression: baseline failures must retain actionable diagnostics."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/genesis-agentic-strategy-worker.yml"


def test_agentic_strategy_pre_evidence_baseline_writes_diagnostic_artifact():
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("      - name: Verify clean repository baseline\n", 2)[-1].split("      - name: Hydrate validated Genesis memory", 1)[0]
    assert "id: baseline" in block
    assert "runtime/github_issue_autorepair.json" in block
    assert '"baseline_tests_failed"' in block
    assert '"failed_tests"' in block
    assert 'exit "$result"' in block


def test_agentic_strategy_release_keeps_pre_evidence_failure_details():
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("      - name: Release unsuccessful Agentic reservation", 1)[1].split("      - name: Preserve Agentic repair evidence", 1)[0]
    assert "runtime/github_issue_autorepair.json" in block
    assert ".reason // .status // empty" in block
    assert "phase,exit_code,diagnosis,failed_tests,run_id" in block
    assert "genesis-agentic-failure-evidence" in block

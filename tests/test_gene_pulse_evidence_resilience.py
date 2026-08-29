from pathlib import Path


WORKFLOW = Path(".github/workflows/gene-pulse.yml")


def test_pulse_falls_back_when_exact_predecessor_cache_is_unavailable() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "id: exact_runtime" in text
    assert "continue-on-error: true" in text
    assert "Restore latest Gene state after predecessor cache failure" in text
    assert "steps.exact_runtime.outcome != 'success'" in text
    assert "restore-keys:" in text


def test_transient_artifact_failure_is_retried_without_terminating_pulse_chain() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "id: upload_evidence" in text
    assert "Retry pulse evidence upload after transient artifact failure" in text
    assert "steps.upload_evidence.outcome == 'failure'" in text
    assert "id: retry_upload_evidence" in text
    assert "Report unavailable pulse evidence service" in text
    assert "Both artifact upload attempts failed" in text
    assert "Request next pulse" in text

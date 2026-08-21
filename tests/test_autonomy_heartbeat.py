from pathlib import Path


def test_autonomy_heartbeat_restarts_idle_pipeline_without_duplicate_work() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "autonomy-heartbeat.yml").read_text(encoding="utf-8")

    assert 'cron: "7 * * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert '".github/workflows/autonomy-heartbeat.yml"' in workflow
    assert "group: genesis-autonomy-heartbeat" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "GH_REPO: ${{ github.repository }}" in workflow

    assert "for workflow in gene-pulse.yml file-self-review.yml manual-self-repair.yml" in workflow
    assert "for status in queued in_progress" in workflow
    assert "freshness_seconds=7200" in workflow
    assert "age <= freshness_seconds" in workflow
    assert "/force-cancel" in workflow
    assert 'if [[ "$workflow" == "gene-pulse.yml" ]]' not in workflow
    assert 'if [[ "$run_status" == "in_progress" ]]' in workflow
    assert "stale_in_progress" in workflow
    assert "stale_cancel_failures" in workflow
    assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0" in workflow
    assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0 || ${#stale_cancel_failures[@]} > 0" not in workflow

    assert "if: steps.gate.outputs.busy == 'false'" in workflow
    assert "gh workflow run gene-pulse.yml" in workflow
    assert "-f continue_chain=true" in workflow
    assert "duplicate Gene Pulse was skipped" in workflow
    assert "Stale in-progress runs" in workflow


def test_manual_and_scheduled_pulse_controls_share_stale_safety_invariants() -> None:
    root = Path(__file__).resolve().parents[1]
    heartbeat = (root / ".github" / "workflows" / "autonomy-heartbeat.yml").read_text(encoding="utf-8")
    manual = (root / ".github" / "workflows" / "pulse-control.yml").read_text(encoding="utf-8")

    for workflow in (heartbeat, manual):
        assert "GH_REPO: ${{ github.repository }}" in workflow
        assert "for workflow in gene-pulse.yml file-self-review.yml manual-self-repair.yml" in workflow
        assert "for status in queued in_progress" in workflow
        assert "freshness_seconds=7200" in workflow
        assert "gh run cancel" in workflow
        assert "/force-cancel" in workflow
        assert "stale_in_progress" in workflow
        assert "stale_cancel_failures" in workflow
        assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0" in workflow
        assert "${#fresh[@]} > 0 || ${#stale_in_progress[@]} > 0 || ${#stale_cancel_failures[@]} > 0" not in workflow
        assert "if: steps.gate.outputs.busy == 'false'" in workflow
        assert "gh workflow run gene-pulse.yml" in workflow
        assert "-f continue_chain=true" in workflow


def test_gene_pulse_remains_bounded_and_self_chaining() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")

    assert "timeout-minutes: 35" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "Request next pulse" in workflow
    assert "steps.pulse.outputs.continue == 'true'" in workflow
    assert "gh workflow run gene-pulse.yml" in workflow

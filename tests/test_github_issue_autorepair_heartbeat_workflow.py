from pathlib import Path


HEARTBEAT = Path(".github/workflows/github-issue-autorepair-heartbeat.yml")


def test_heartbeat_uses_gene_pulse_and_schedule_as_independent_wakeup_paths() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert 'workflows: ["Gene Pulse"]' in text
    assert "types: [completed]" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "cron: '*/5 * * * *'" in text
    assert "push:" in text
    assert "github-issue-autorepair.yml" in text


def test_heartbeat_cannot_claim_or_mutate_issues() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "issues: read" in text
    assert "issues: write" not in text
    assert "--add-label genesis-repair-in-progress" not in text
    assert "--remove-label genesis-repair-in-progress" not in text
    assert "gh issue edit" not in text


def test_heartbeat_preserves_single_lane_capacity_and_queue_filters() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '1'" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert 'index("genesis-validating")' in text
    assert 'index("genesis-autonomous")' in text
    assert 'index("genesis-task")' in text
    assert 'index("genesis-blocked")' in text
    assert 'index("genesis-solved")' in text
    assert "available=$((GENESIS_ISSUE_REPAIR_MAX_PARALLEL - active))" in text
    assert "if (( launch_count > 0 )); then" in text


def test_heartbeat_dispatches_explicit_issue_to_authoritative_dispatcher_only() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "mapfile -t selected" in text
    assert "gh workflow run github-issue-autorepair.yml" in text
    assert "--ref main" in text
    assert '-f issue_number="$issue_number"' in text
    assert "gh workflow run github-issue-autorepair-worker.yml" not in text
    assert "gh workflow run github-issue-autorepair-integration.yml" not in text

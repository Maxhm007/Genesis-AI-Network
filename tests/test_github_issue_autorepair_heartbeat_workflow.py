from pathlib import Path


HEARTBEAT = Path(".github/workflows/github-issue-autorepair-heartbeat.yml")


def test_heartbeat_uses_gene_pulse_as_independent_wakeup_path() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert 'workflows: ["Gene Pulse"]' in text
    assert "types: [completed]" in text
    assert "workflow_dispatch:" in text
    assert "push:" in text
    assert "github-issue-autorepair.yml" in text


def test_heartbeat_cannot_claim_or_mutate_issues() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "issues: read" in text
    assert "issues: write" not in text
    assert "--add-label genesis-repair-in-progress" not in text
    assert "--remove-label genesis-repair-in-progress" not in text


def test_heartbeat_preserves_three_worker_capacity_and_queue_filters() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '3'" in text
    assert 'index("genesis-repair-in-progress")' in text
    assert 'index("genesis-validating")' in text
    assert 'index("genesis-autonomous")' in text
    assert 'index("genesis-blocked")' in text
    assert 'index("genesis-solved")' in text
    assert "active < GENESIS_ISSUE_REPAIR_MAX_PARALLEL && eligible > 0" in text


def test_heartbeat_only_wakes_existing_authoritative_dispatcher() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "gh workflow run github-issue-autorepair.yml" in text
    assert "--ref main" in text
    assert "github-issue-autorepair-worker.yml" not in text
    assert "github-issue-autorepair-integration.yml" not in text

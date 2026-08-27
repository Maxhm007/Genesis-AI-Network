from pathlib import Path


AUTONOMY = Path(".github/workflows/autonomy-heartbeat.yml")
AUTOREPAIR = Path(".github/workflows/github-issue-autorepair.yml")


def test_autonomy_heartbeat_checks_every_five_minutes_but_adapts_dispatch() -> None:
    text = AUTONOMY.read_text(encoding="utf-8")
    assert 'cron: "*/5 * * * *"' in text
    assert 'workflows: ["Genesis GitHub Issue Autorepair"]' in text
    assert "adaptive_recovery_interval" in text
    assert "recovery_pulse_due" in text
    assert "DESIRED_INTERVAL_MINUTES" in text
    assert "steps.gate.outputs.pulse_due == 'true'" in text
    assert "issues: read" in text


def test_autorepair_admission_is_event_driven_for_open_and_reopen() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")
    assert "types: [opened, reopened, labeled]" in text
    assert "github.event_name != 'issues' ||" in text
    assert "github.event.action != 'labeled' ||" in text
    assert "github.event.label.name == 'genesis-autonomous'" in text
    assert "github.event.label.name == 'genesis-task'" in text


def test_autorepair_still_refills_immediately_and_keeps_five_lane_capacity() -> None:
    text = AUTOREPAIR.read_text(encoding="utf-8")
    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: '5'" in text
    assert "refill:" in text
    assert "gh workflow run github-issue-autorepair-heartbeat.yml" in text
    assert "github-issue-autorepair-integration.yml" in text

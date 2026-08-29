from pathlib import Path

from genesis.issue_worker_pool import select_issue_repair_batch


HEARTBEAT = Path(".github/workflows/github-issue-autorepair-heartbeat.yml")


def _issue(number: int, *labels: str, title: str = "") -> dict:
    return {
        "number": number,
        "state": "OPEN",
        "updatedAt": f"2026-08-26T00:{number:02d}:00Z",
        "title": title,
        "labels": [{"name": label} for label in labels],
    }


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
    # Module execution keeps the repository root on sys.path so the script can
    # import the shared genesis selector in a clean GitHub Actions checkout.
    assert "python -m scripts.select_issue_repair_batch" in text
    assert '--issues-json "$RUNNER_TEMP/open-issues.json"' in text
    assert '--max-parallel "$GENESIS_ISSUE_REPAIR_MAX_PARALLEL"' in text
    assert ".selected_issue_numbers[]" in text
    assert ".active_issue_numbers | length" in text
    assert ".available_slots" in text
    assert 'index("genesis-validating")' in text
    assert 'index("genesis-autonomous")' in text
    assert "if (( launch_count > 0 )); then" in text


def test_heartbeat_does_not_maintain_a_second_divergent_eligibility_filter() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "eligible_filter=" not in text
    assert 'startswith("[Genesis Self Improvement]")' not in text


def test_shared_selector_excludes_non_generic_queue_records() -> None:
    rows = [
        _issue(24, "genesis-task", "duplicate"),
        _issue(25, "genesis-task", "genesis-persistent"),
        _issue(26, "genesis-task", "genesis-control"),
        _issue(27, "genesis-task", title="Genesis Control: persistent dashboard"),
        _issue(28, "genesis-task", title="[Genesis Self Improvement] specialist work"),
        _issue(29, "genesis-task", title="[Genesis Repair] repair the queue"),
    ]

    batch = select_issue_repair_batch(rows, max_parallel=1)

    assert batch.selected_issue_numbers == (29,)


def test_heartbeat_dispatches_explicit_issue_to_authoritative_dispatcher_only() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")

    assert "mapfile -t selected" in text
    assert "gh workflow run github-issue-autorepair.yml" in text
    assert "--ref main" in text
    assert '-f issue_number="$issue_number"' in text
    assert "gh workflow run github-issue-autorepair-worker.yml" not in text
    assert "gh workflow run github-issue-autorepair-integration.yml" not in text

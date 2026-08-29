from genesis.issue_worker_pool import select_issue_repair_batch


def _issue(
    number: int,
    created: str,
    *labels: str,
    title: str = "",
    updated: str | None = None,
) -> dict:
    return {
        "number": number,
        "state": "OPEN",
        "createdAt": created,
        "updatedAt": updated or created,
        "title": title,
        "labels": [{"name": label} for label in labels],
    }


def test_selects_five_distinct_oldest_eligible_issues() -> None:
    rows = [
        _issue(6, "2026-08-26T06:00:00Z", "genesis-autonomous"),
        _issue(4, "2026-08-26T04:00:00Z", "genesis-autonomous"),
        _issue(2, "2026-08-26T02:00:00Z", "genesis-autonomous"),
        _issue(5, "2026-08-26T05:00:00Z", "genesis-autonomous"),
        _issue(3, "2026-08-26T03:00:00Z", "genesis-autonomous"),
        _issue(1, "2026-08-26T01:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.selected_issue_numbers == (1, 2, 3, 4, 5)
    assert batch.available_slots == 5


def test_active_repair_and_validation_both_consume_capacity() -> None:
    rows = [
        _issue(10, "2026-08-26T01:00:00Z", "genesis-repair-in-progress"),
        _issue(11, "2026-08-26T02:00:00Z", "genesis-validating"),
        _issue(12, "2026-08-26T03:00:00Z", "genesis-autonomous"),
        _issue(13, "2026-08-26T04:00:00Z", "genesis-autonomous"),
        _issue(14, "2026-08-26T05:00:00Z", "genesis-autonomous"),
        _issue(15, "2026-08-26T06:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.active_issue_numbers == (10, 11)
    assert batch.available_slots == 3
    assert batch.selected_issue_numbers == (12, 13, 14)


def test_blocked_solved_and_claimed_issues_are_not_selected() -> None:
    rows = [
        _issue(20, "2026-08-26T01:00:00Z", "genesis-autonomous", "genesis-blocked"),
        _issue(21, "2026-08-26T02:00:00Z", "genesis-autonomous", "genesis-solved"),
        _issue(22, "2026-08-26T03:00:00Z", "genesis-autonomous", "genesis-repair-in-progress"),
        _issue(23, "2026-08-26T04:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.selected_issue_numbers == (23,)


def test_non_code_issue_backed_tasks_stay_out_of_generic_autorepair() -> None:
    rows = [
        _issue(
            40,
            "2026-08-26T01:00:00Z",
            "genesis-autonomous",
            "genesis-self-improvement",
            title="[Genesis Self Improvement] competitive ai improvement — frontier benchmarks",
        ),
        _issue(
            41,
            "2026-08-26T02:00:00Z",
            "genesis-task",
            "genesis-autonomous",
            title="[Genesis Task] competitive ai improvement — Measure the weakest frontier dimension",
        ),
        _issue(
            42,
            "2026-08-26T03:00:00Z",
            "genesis-task",
            "genesis-autonomous",
            title="[Genesis Task] competitive reference refresh — Refresh official frontier evidence",
        ),
        _issue(
            43,
            "2026-08-26T04:00:00Z",
            "genesis-task",
            "genesis-autonomous",
            title="[Genesis Task] immortality research — Review new evidence",
        ),
        _issue(
            44,
            "2026-08-26T05:00:00Z",
            "genesis-autonomous",
            title="[Genesis Repair] concrete software defect",
        ),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.selected_issue_numbers == (44,)
    assert select_issue_repair_batch(rows, explicit_issue_number=40).selected_issue_numbers == ()
    assert select_issue_repair_batch(rows, explicit_issue_number=41).selected_issue_numbers == ()


def test_older_general_issue_beats_newer_repair_issue() -> None:
    rows = [
        _issue(
            70,
            "2026-08-20T01:00:00Z",
            "genesis-autonomous",
            title="[Genesis Task] ordinary older repairable work",
        ),
        _issue(
            71,
            "2026-08-21T01:00:00Z",
            "genesis-autonomous",
            title="[Genesis Repair] newer urgent-looking work",
        ),
    ]

    batch = select_issue_repair_batch(rows, max_parallel=1)

    assert batch.selected_issue_numbers == (70,)


def test_updated_at_does_not_change_fifo_position() -> None:
    rows = [
        _issue(
            80,
            "2026-08-20T01:00:00Z",
            "genesis-autonomous",
            updated="2026-08-29T23:59:00Z",
        ),
        _issue(
            81,
            "2026-08-21T01:00:00Z",
            "genesis-autonomous",
            updated="2026-08-21T01:00:00Z",
        ),
    ]

    batch = select_issue_repair_batch(rows, max_parallel=1)

    assert batch.selected_issue_numbers == (80,)


def test_explicit_newer_issue_cannot_bypass_oldest_eligible_issue() -> None:
    rows = [
        _issue(90, "2026-08-20T01:00:00Z", "genesis-autonomous"),
        _issue(91, "2026-08-21T01:00:00Z", "genesis-autonomous"),
    ]

    assert select_issue_repair_batch(rows, explicit_issue_number=91).selected_issue_numbers == ()
    assert select_issue_repair_batch(rows, explicit_issue_number=90).selected_issue_numbers == (90,)


def test_missing_or_equal_created_at_uses_issue_number_deterministically() -> None:
    rows = [
        {
            "number": 102,
            "state": "OPEN",
            "title": "",
            "labels": [{"name": "genesis-autonomous"}],
        },
        {
            "number": 101,
            "state": "OPEN",
            "title": "",
            "labels": [{"name": "genesis-autonomous"}],
        },
    ]

    assert select_issue_repair_batch(rows, max_parallel=1).selected_issue_numbers == (101,)


def test_explicit_manual_issue_does_not_bypass_authorization_or_capacity() -> None:
    unauthorized = [_issue(30, "2026-08-26T01:00:00Z")]
    assert select_issue_repair_batch(unauthorized, explicit_issue_number=30).selected_issue_numbers == ()

    full = [
        _issue(31, "2026-08-26T01:00:00Z", "genesis-repair-in-progress"),
        _issue(32, "2026-08-26T02:00:00Z", "genesis-validating"),
        _issue(33, "2026-08-26T03:00:00Z", "genesis-validating"),
        _issue(34, "2026-08-26T04:00:00Z", "genesis-repair-in-progress"),
        _issue(35, "2026-08-26T05:00:00Z", "genesis-validating"),
        _issue(36, "2026-08-26T06:00:00Z", "genesis-autonomous"),
    ]
    assert select_issue_repair_batch(full, explicit_issue_number=36).selected_issue_numbers == ()

from genesis.issue_worker_pool import select_issue_repair_batch


def _issue(number: int, updated: str, *labels: str) -> dict:
    return {
        "number": number,
        "state": "OPEN",
        "updatedAt": updated,
        "labels": [{"name": label} for label in labels],
    }


def test_selects_three_distinct_oldest_eligible_issues() -> None:
    rows = [
        _issue(4, "2026-08-26T04:00:00Z", "genesis-autonomous"),
        _issue(2, "2026-08-26T02:00:00Z", "genesis-autonomous"),
        _issue(3, "2026-08-26T03:00:00Z", "genesis-autonomous"),
        _issue(1, "2026-08-26T01:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.selected_issue_numbers == (1, 2, 3)
    assert batch.available_slots == 3


def test_active_repair_and_validation_both_consume_capacity() -> None:
    rows = [
        _issue(10, "2026-08-26T01:00:00Z", "genesis-repair-in-progress"),
        _issue(11, "2026-08-26T02:00:00Z", "genesis-validating"),
        _issue(12, "2026-08-26T03:00:00Z", "genesis-autonomous"),
        _issue(13, "2026-08-26T04:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.active_issue_numbers == (10, 11)
    assert batch.available_slots == 1
    assert batch.selected_issue_numbers == (12,)


def test_blocked_solved_and_claimed_issues_are_not_selected() -> None:
    rows = [
        _issue(20, "2026-08-26T01:00:00Z", "genesis-autonomous", "genesis-blocked"),
        _issue(21, "2026-08-26T02:00:00Z", "genesis-autonomous", "genesis-solved"),
        _issue(22, "2026-08-26T03:00:00Z", "genesis-autonomous", "genesis-repair-in-progress"),
        _issue(23, "2026-08-26T04:00:00Z", "genesis-autonomous"),
    ]

    batch = select_issue_repair_batch(rows)

    assert batch.selected_issue_numbers == (23,)


def test_explicit_manual_issue_does_not_bypass_authorization_or_capacity() -> None:
    unauthorized = [_issue(30, "2026-08-26T01:00:00Z")]
    assert select_issue_repair_batch(unauthorized, explicit_issue_number=30).selected_issue_numbers == ()

    full = [
        _issue(31, "2026-08-26T01:00:00Z", "genesis-repair-in-progress"),
        _issue(32, "2026-08-26T02:00:00Z", "genesis-validating"),
        _issue(33, "2026-08-26T03:00:00Z", "genesis-validating"),
        _issue(34, "2026-08-26T04:00:00Z", "genesis-autonomous"),
    ]
    assert select_issue_repair_batch(full, explicit_issue_number=34).selected_issue_numbers == ()

from __future__ import annotations

from genesis.issue_lifecycle import family_ids_for_issue, family_status, lifecycle_decision, local_claim_block_reason


def issue(
    number: int,
    *,
    state: str = "open",
    labels=(),
    body: str = "",
    state_reason: str = "",
    created_at: str = "",
    closed_at: str = "",
) -> dict:
    return {
        "number": number,
        "state": state,
        "state_reason": state_reason,
        "labels": [{"name": label} for label in labels],
        "body": body,
        "created_at": created_at,
        "closed_at": closed_at,
    }


def test_verified_root_supersedes_open_successor():
    root = issue(500, state="closed", labels=("genesis-task", "genesis-verified"))
    successor = issue(
        797,
        labels=("genesis-task", "agentic-lab"),
        body="<!-- genesis-unsolved-root:500 -->\n<!-- genesis-unsolved-successor-of:500 -->",
    )

    decision = lifecycle_decision(successor, {500: root, 797: successor})

    assert decision.action == "close_superseded"
    assert decision.reference_issue == 500


def test_verified_equivalent_problem_closes_duplicate():
    solved = issue(
        760,
        state="closed",
        labels=("genesis-task", "genesis-verified"),
        body=(
            "Genesis-Problem-Fingerprint: dashboard-review:abc\n"
            "Genesis-Occurrence-Fingerprint: dashboard-occurrence:one"
        ),
    )
    duplicate = issue(
        806,
        labels=("genesis-task", "agentic-lab"),
        body=(
            "Genesis-Problem-Fingerprint: dashboard-review:abc\n"
            "Genesis-Occurrence-Fingerprint: dashboard-occurrence:one"
        ),
    )

    decision = lifecycle_decision(duplicate, {760: solved, 806: duplicate})

    assert decision.action == "close_duplicate"
    assert decision.reference_issue == 760


def test_superseded_closed_issue_is_never_reopened_by_stale_solver_labels():
    stale = issue(
        814,
        state="closed",
        state_reason="duplicate",
        labels=("genesis-task", "genesis-superseded", "genesis-solver-exhausted"),
    )

    decision = lifecycle_decision(stale, {814: stale})

    assert decision.action == "keep_closed"
    assert local_claim_block_reason(stale) == "closed"


def test_orphan_capability_dependency_is_retired():
    parent = issue(797, state="closed", labels=("genesis-task", "genesis-superseded"))
    capability = issue(
        869,
        labels=("genesis-task", "agentic-lab"),
        body=(
            "<!-- genesis-capability-work:abc -->\n"
            "<!-- genesis-capability-parent:797 -->\n"
            "- **Task type:** `capability_growth`"
        ),
    )

    decision = lifecycle_decision(capability, {797: parent, 869: capability})

    assert decision.action == "close_superseded"
    assert decision.reason == "no_live_capability_parent"


def test_authoritative_unverified_root_may_reopen():
    root = issue(
        500,
        state="closed",
        labels=("genesis-task", "genesis-solver-exhausted"),
        body="root objective",
    )

    decision = lifecycle_decision(root, {500: root})

    assert decision.action == "reopen"


def test_infrastructure_quarantine_blocks_claim():
    current = issue(760, labels=("genesis-task", "agentic-lab"))
    comments = [{"body": "<!-- genesis-agentic-infrastructure-quarantine -->"}]

    assert local_claim_block_reason(current, comments) == "infrastructure_quarantine"


def test_fresh_post_fix_regression_is_not_suppressed():
    solved = issue(
        10,
        state="closed",
        labels=("genesis-task", "genesis-verified"),
        body=(
            "Genesis-Problem-Fingerprint: genesis-problem:abc\n"
            "Genesis-Occurrence-Fingerprint: genesis-occurrence:old"
        ),
        created_at="2026-09-01T00:00:00Z",
        closed_at="2026-09-02T00:00:00Z",
    )
    regression = issue(
        11,
        labels=("genesis-task",),
        body=(
            "Genesis-Problem-Fingerprint: genesis-problem:abc\n"
            "Genesis-Occurrence-Fingerprint: genesis-occurrence:new"
        ),
        created_at="2026-09-03T00:00:00Z",
    )

    decision = lifecycle_decision(regression, {10: solved, 11: regression})

    assert decision.action == "keep_open"


def test_open_legacy_successor_is_superseded_while_root_unresolved():
    root = issue(802, labels=("genesis-task", "genesis-autonomous"))
    successor = issue(
        809,
        labels=("genesis-task", "agentic-lab"),
        body="<!-- genesis-unsolved-root:802 -->\n<!-- genesis-unsolved-successor-of:802 -->",
    )

    decision = lifecycle_decision(successor, {802: root, 809: successor})

    assert decision.action == "close_superseded"
    assert decision.reason == "authoritative_root_unresolved"
    assert decision.reference_issue == 802


def test_family_status_keeps_unresolved_root_as_only_authority():
    root = issue(802, labels=("genesis-task",))
    successor = issue(
        809,
        body="<!-- genesis-unsolved-root:802 -->\n<!-- genesis-unsolved-successor-of:802 -->",
    )

    status = family_status(802, {802: root, 809: successor})

    assert status["family_id"] == "genesis-family:802"
    assert status["root"] == 802
    assert status["current_authority"] == 802
    assert status["members"] == (802, 809)
    assert status["successors"] == (809,)


def test_shared_capability_issue_belongs_to_multiple_root_families():
    root_a = issue(100, labels=("genesis-task",))
    root_b = issue(200, labels=("genesis-task",))
    capability = issue(
        300,
        body=(
            "<!-- genesis-capability-work:abc -->\n"
            "<!-- genesis-capability-parent:100 -->\n"
            "- **Task type:** `capability_growth`"
        ),
    )
    comments = [{"body": "<!-- genesis-capability-parent:200 -->"}]

    families = family_ids_for_issue(
        capability,
        {100: root_a, 200: root_b, 300: capability},
        comments=comments,
    )

    assert families == ("genesis-family:100", "genesis-family:200")


def test_family_status_shows_capability_dependency_and_release():
    root = issue(400, labels=("genesis-task",))
    capability = issue(
        500,
        body=(
            "<!-- genesis-capability-work:xyz -->\n"
            "<!-- genesis-capability-parent:400 -->"
        ),
    )
    comments = {
        400: [
            {"body": "<!-- genesis-agentic-capability-dependency:500 -->"},
        ],
        500: [],
    }

    status = family_status(400, {400: root, 500: capability}, comments_by_number=comments)
    assert status["capability_dependencies"] == (500,)
    assert status["shared_capabilities"] == (500,)
    assert status["chain"] == ("root:400", "capability:500")

    comments[400].append({"body": "<!-- genesis-agentic-capability-release:500 -->"})
    released = family_status(400, {400: root, 500: capability}, comments_by_number=comments)
    assert released["capability_dependencies"] == ()
    assert released["shared_capabilities"] == (500,)
    assert released["released_capabilities"] == (500,)
    assert released["chain"] == ("root:400", "resumed:400")

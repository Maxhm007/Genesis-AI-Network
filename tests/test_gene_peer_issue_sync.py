from scripts.gene_peer_issue_sync import (
    PeerIssue,
    canonical_body,
    canonical_title,
    choose_new_peer_issue,
    is_actionable,
)


def peer(number=1, title="Fix parser", body="Objective: fix parser\nAcceptance: tests pass"):
    return PeerIssue(
        gene="Gene 002",
        repository="Maxhm007/Genesis-Node-2",
        number=number,
        title=title,
        body=body,
        html_url=f"https://github.com/Maxhm007/Genesis-Node-2/issues/{number}",
    )


def test_actionable_peer_issue_requires_open_problem_shape():
    assert is_actionable({"number": 1, "state": "open", "title": "Repair bug", "body": "Acceptance: tests pass"})
    assert not is_actionable({"number": 1, "state": "closed", "title": "Repair bug", "body": "Acceptance: tests pass"})
    assert not is_actionable({"number": 1, "state": "open", "title": "FYI", "body": "hello"})
    assert not is_actionable({"number": 1, "state": "open", "title": "Repair", "body": "Acceptance: tests pass", "pull_request": {}})


def test_canonical_copy_preserves_peer_provenance_and_authority():
    row = peer()
    body = canonical_body(row)
    assert row.marker in body
    assert "Source Gene" in body
    assert "Gene 0 owns the canonical issue lifecycle" in body
    assert canonical_title(row).startswith("[Peer Sync][Gene 002]")


def test_deduplicates_same_peer_issue():
    row = peer()
    assert choose_new_peer_issue([row], [canonical_body(row)]) is None


def test_selects_oldest_new_peer_issue_deterministically():
    later = peer(9)
    earlier = peer(3)
    chosen = choose_new_peer_issue([later, earlier], [])
    assert chosen is not None
    assert chosen.number == 3

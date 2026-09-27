from datetime import datetime, timedelta, timezone
import json

from genesis.architecture_extensions.architecture_route_gene_0_backlog_work_to_idle_gene_002_and_gene_003 import (
    BacklogDelegationRouter,
)


def _issue(number: int, title: str = "Implement repair", body: str = "") -> dict:
    return {"number": number, "title": title, "body": body}


def test_detects_backlog_pressure_and_idle_specialist(tmp_path):
    router = BacklogDelegationRouter(tmp_path, backlog_threshold=3)

    assert router.should_delegate(
        gene0_open_count=5,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 1},
        capability="research",
    ) == (True, "eligible")
    assert router.should_delegate(
        gene0_open_count=5,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 1},
        capability="repair",
    ) == (False, "supporting_gene_busy")
    assert router.should_delegate(
        gene0_open_count=2,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 0},
        capability="validation",
    ) == (False, "backlog_below_threshold")


def test_routes_research_to_gene002_and_repair_to_gene003(tmp_path):
    router = BacklogDelegationRouter(tmp_path)

    research = router.delegate(
        _issue(10, "Research validation evidence"),
        gene0_open_count=6,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 0},
        target="docs/evidence.md",
        capability="research",
    )
    repair = router.delegate(
        _issue(11, "Repair workflow failure"),
        gene0_open_count=6,
        peer_open_counts={"gene-node-2": 1, "gene-node-3": 0},
        target="scripts/repair.py",
        capability="repair",
    )

    assert research["status"] == "delegated"
    assert research["task"]["peer_logical_id"] == "gene-node-2"
    assert research["task"]["authoritative_repo"] == "Maxhm007/Genesis-AI-Network"
    assert repair["status"] == "delegated"
    assert repair["task"]["peer_logical_id"] == "gene-node-3"


def test_prevents_conflicting_target_leases(tmp_path):
    router = BacklogDelegationRouter(tmp_path)
    peers = {"gene-node-2": 0, "gene-node-3": 0}

    first = router.delegate(
        _issue(20),
        gene0_open_count=5,
        peer_open_counts=peers,
        target="genesis/shared.py",
        capability="repair",
    )
    second = router.delegate(
        _issue(21, "Validate same target"),
        gene0_open_count=5,
        peer_open_counts=peers,
        target="genesis/shared.py",
        capability="validation",
    )

    assert first["status"] == "delegated"
    assert second == {"status": "rejected", "reason": "target_conflict"}


def test_reclaims_expired_lease(tmp_path):
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    router = BacklogDelegationRouter(tmp_path, lease_seconds=60)
    delegated = router.delegate(
        _issue(30),
        gene0_open_count=5,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 0},
        target="scripts/repair.py",
        capability="repair",
        now=now,
    )
    assert delegated["status"] == "delegated"

    reclaimed = router.reclaim_expired(now=now + timedelta(seconds=61))

    assert len(reclaimed) == 1
    assert reclaimed[0]["parent_issue"] == 30
    assert reclaimed[0]["status"] == "reclaimed"


def test_accepts_only_signed_hash_verified_independently_validated_result(tmp_path):
    router = BacklogDelegationRouter(tmp_path)
    delegated = router.delegate(
        _issue(40),
        gene0_open_count=5,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 0},
        target="genesis/repair.py",
        capability="repair",
    )
    task_id = delegated["task"]["task_id"]
    output = {"finding": "bounded candidate", "checks": ["unit", "security"]}
    claimed_hash = router.peer_compute.hash_payload(output)
    signed_result = router.peer_network.send_message(
        "gene-node-3",
        "gene-node-1",
        subject="Delegated work result",
        body=json.dumps({"task_id": task_id, "provenance": {"source": "Gene 003"}}, sort_keys=True),
        message_type="delegated_work_result",
    )

    rejected = router.ingest_result(
        signed_message=signed_result,
        output=output,
        claimed_output_hash=claimed_hash,
        independently_validated=False,
    )
    accepted = router.ingest_result(
        signed_message=signed_result,
        output=output,
        claimed_output_hash=claimed_hash,
        independently_validated=True,
    )

    assert rejected == {"status": "rejected", "reason": "independent_validation_required"}
    assert accepted["status"] == "accepted_evidence"
    assert accepted["parent_issue"] == 40
    assert accepted["closure_authority"] == "Gene 0"


def test_invalid_signature_is_rejected(tmp_path):
    router = BacklogDelegationRouter(tmp_path)
    delegated = router.delegate(
        _issue(50),
        gene0_open_count=5,
        peer_open_counts={"gene-node-2": 0, "gene-node-3": 0},
        target="docs/review.md",
        capability="review",
    )
    task_id = delegated["task"]["task_id"]
    output = {"review": "ok"}
    signed_result = router.peer_network.send_message(
        "gene-node-2",
        "gene-node-1",
        subject="Delegated work result",
        body=json.dumps({"task_id": task_id}),
        message_type="delegated_work_result",
    )
    signed_result["body"] = json.dumps({"task_id": task_id, "tampered": True})

    result = router.ingest_result(
        signed_message=signed_result,
        output=output,
        claimed_output_hash=router.peer_compute.hash_payload(output),
        independently_validated=True,
    )

    assert result == {"status": "rejected", "reason": "invalid_signature"}



def test_pulse_integrates_delegation_router():
    text = __import__("pathlib").Path("genesis/pulse.py").read_text(encoding="utf-8")
    assert "BacklogDelegationRouter" in text
    assert 'payload["delegation_reclaimed"]' in text
    assert 'payload["delegated_work_inbox"]' in text
    assert '"gene-node-2", "gene-node-3"' in text

from __future__ import annotations

from genesis.learned_capabilities import run_capability


def test_persistent_memory_store_is_candidate_until_validated(tmp_path):
    stored = run_capability(
        "persistent_memory",
        "store",
        root=tmp_path,
        memory_type="repair",
        topic="issue-829",
        content="Rebase autonomous candidates onto current main before publication.",
        source_type="github_issue",
        source_ref="#829",
        confidence=0.9,
        importance=0.9,
        metadata={"provider": "genesis-bounded-repair"},
    )

    assert stored["state"] == "candidate"
    assert stored["source_type"] == "github_issue"
    assert stored["source_ref"] == "#829"

    assert run_capability(
        "persistent_memory",
        "recall",
        root=tmp_path,
        query="rebase autonomous candidates",
    ) == []

    validated = run_capability(
        "persistent_memory",
        "validate",
        root=tmp_path,
        memory_id=stored["memory_id"],
        evidence={"worker_run": 35439082677, "full_suite_passed": True},
    )
    assert validated["state"] == "validated"
    assert validated["metadata"]["validation"]["full_suite_passed"] is True


def test_persistent_memory_survives_new_capability_invocation(tmp_path):
    stored = run_capability(
        "persistent_memory",
        "store",
        root=tmp_path,
        memory_type="decision",
        topic="issue-family-authority",
        content="Keep one authoritative root issue across retries.",
        source_type="architecture_issue",
        source_ref="#865",
    )
    run_capability(
        "persistent_memory",
        "validate",
        root=tmp_path,
        memory_id=stored["memory_id"],
        evidence={"issue": 865, "verified": True},
    )

    recalled = run_capability(
        "persistent_memory",
        "recall",
        root=tmp_path,
        query="authoritative root issue retries",
    )

    assert len(recalled) == 1
    assert recalled[0]["memory_id"] == stored["memory_id"]
    assert recalled[0]["memory_type"] == "decision"


def test_persistent_memory_reject_and_expire_remove_from_normal_recall(tmp_path):
    rejected = run_capability(
        "persistent_memory",
        "store",
        root=tmp_path,
        memory_type="semantic",
        topic="bad-fact",
        content="Temporary unverified claim about dashboard behavior.",
        source_type="analysis",
        source_ref="trial-1",
    )
    run_capability(
        "persistent_memory",
        "reject",
        root=tmp_path,
        memory_id=rejected["memory_id"],
        evidence={"reason": "contradicted by current repository state"},
    )

    assert run_capability(
        "persistent_memory",
        "recall",
        root=tmp_path,
        query="dashboard behavior",
    ) == []


def test_persistent_memory_is_idempotent_for_same_provenance_and_content(tmp_path):
    kwargs = dict(
        root=tmp_path,
        memory_type="episodic",
        topic="repair-run",
        content="Worker validated current main successfully.",
        source_type="workflow_run",
        source_ref="35439082677",
    )
    first = run_capability("persistent_memory", "store", **kwargs)
    second = run_capability("persistent_memory", "store", **kwargs)

    assert first["memory_id"] == second["memory_id"]
    stats = run_capability("persistent_memory", "stats", root=tmp_path)
    assert stats["total"] == 1


def test_persistent_memory_recall_is_bounded(tmp_path):
    with __import__("pytest").raises(ValueError, match="recall limit is out of bounds"):
        run_capability(
            "persistent_memory",
            "recall",
            root=tmp_path,
            query="anything",
            limit=21,
        )


def test_persistent_memory_requires_existing_root(tmp_path):
    missing = tmp_path / "missing"
    with __import__("pytest").raises(ValueError, match="existing Genesis directory"):
        run_capability("persistent_memory", "stats", root=missing)

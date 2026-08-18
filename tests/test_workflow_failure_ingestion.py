from __future__ import annotations

from pathlib import Path

from scripts.ingest_workflow_failure import ingest
from genesis.modules.task_queue import PersistentTaskQueue


def test_failed_workflow_becomes_persistent_gaps_task(tmp_path: Path) -> None:
    result = ingest(
        tmp_path,
        repository="owner/repo",
        run_id="123",
        workflow="Genesis Candidate PR Gate",
        conclusion="failure",
        head_branch="genesis/candidate-example",
        head_sha="abc123",
        logs="pytest failed: AssertionError: expected validated candidate",
    )
    assert result["task_created"] is True
    assert result["gaps"]["diagnosis"]["classification"] == "test_or_validation_regression"
    queue = PersistentTaskQueue(tmp_path / "runtime" / "genesis_tasks.sqlite3")
    task = queue.get(result["task_id"])
    assert task is not None
    assert task.state == "failed"
    assert task.payload["head_branch"] == "genesis/candidate-example"
    assert task.payload["repair_target"] == "candidate_branch"


def test_same_workflow_run_is_deduplicated(tmp_path: Path) -> None:
    kwargs = dict(
        repository="owner/repo",
        run_id="456",
        workflow="Genesis Secret Guard",
        conclusion="failure",
        head_branch="genesis/candidate-example",
        head_sha="def456",
        logs="secret guard credential-like content detected",
    )
    first = ingest(tmp_path, **kwargs)
    second = ingest(tmp_path, **kwargs)
    assert first["task_created"] is True
    assert second["task_created"] is False
    assert second["task_id"] == first["task_id"]
    assert second["gaps"]["diagnosis"]["classification"] == "security_rejection"


def test_provider_quota_is_not_misdiagnosed_as_code_failure(tmp_path: Path) -> None:
    result = ingest(
        tmp_path,
        repository="owner/repo",
        run_id="789",
        workflow="External Review",
        conclusion="failure",
        head_branch="genesis/candidate-example",
        head_sha="ghi789",
        logs="usage limits reached; external authority requires account credits",
    )
    assert result["gaps"]["diagnosis"]["classification"] == "external_authority"
    assert result["gaps"]["diagnosis"]["owner_action_required"] is True

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import genesis.current_main_review as current_main_review
from genesis.autonomy_pipeline import PipelineRecord


class _TimeoutProvider:
    name = "test-review-provider"

    def reason(self, prompt: str) -> str:
        del prompt
        raise TimeoutError("timed out")


class _Queue:
    def get(self, task_id: str):
        del task_id
        return SimpleNamespace(objective="Improve measured software engineering capability")


class _Coding:
    def _provider(self):
        return _TimeoutProvider()


class _Store:
    def __init__(self, record: PipelineRecord) -> None:
        self.record = record

    def transition(self, task_id: str, stage: str, **kwargs):
        assert task_id == self.record.task_id
        self.record = replace(
            self.record,
            stage=stage,
            last_feedback=kwargs.get("feedback"),
            review_attempts=self.record.review_attempts + (1 if kwargs.get("bump_review") else 0),
        )
        return self.record


class _Worker:
    MAX_FEEDBACK_BYTES = 6000
    MAX_DIFF_BYTES = 12000

    def __init__(self, tmp_path, record: PipelineRecord) -> None:
        self.root = tmp_path
        self.store = _Store(record)
        self.engineering = SimpleNamespace(queue=_Queue(), coding=_Coding())

    def _send_back(self, record: PipelineRecord, feedback: str):
        raise AssertionError(f"advisory provider failure must not send candidate back: {record.task_id}: {feedback}")


def test_provider_timeout_is_advisory_after_current_main_tests_pass(monkeypatch, tmp_path) -> None:
    record = PipelineRecord(
        task_id="task-review-timeout",
        stage="review_ready",
        target_path="genesis/coding.py",
        candidate_branch="genesis/candidate-review-timeout",
        candidate_sha="deadbeef",
        review_ref="genesis/review-deadbeef",
        development_attempts=1,
        repair_attempts=0,
        review_attempts=0,
        last_feedback=None,
        discovery={},
        history=(),
        updated_at="2026-08-24T00:00:00+00:00",
    )
    worker = _Worker(tmp_path, record)

    monkeypatch.setattr(
        current_main_review,
        "_prepare_candidate_on_current_main",
        lambda worker, record: (True, "", "diff --git a/genesis/coding.py b/genesis/coding.py\n", "mainsha"),
    )
    monkeypatch.setattr(
        current_main_review.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="603 passed", stderr=""),
    )
    monkeypatch.setattr(
        current_main_review,
        "_restore_exact_candidate",
        lambda worker, candidate_sha: (True, ""),
    )

    result = current_main_review._run_review_on_current_main(worker, record)

    assert result["action"] == "pipeline_internal_review_approved"
    assert result["model_check_status"] == "skipped_error"
    assert result["record"]["stage"] == "validation_ready"
    assert "model_check_error_skipped:TimeoutError:timed out" in result["record"]["last_feedback"]

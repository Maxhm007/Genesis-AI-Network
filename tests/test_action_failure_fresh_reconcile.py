from scripts import action_failure_fresh_reconcile as reconcile


def test_matching_job_requires_exact_failed_job_success():
    jobs = [
        {"name": "validator_a", "conclusion": "success"},
        {"name": "validator_b", "conclusion": "failure"},
    ]
    assert reconcile._matching_job_passed(jobs, "validator_a") is True
    assert reconcile._matching_job_passed(jobs, "validator_b") is False
    assert reconcile._matching_job_passed(jobs, "validator") is False
    assert reconcile._matching_job_passed(jobs, "workflow") is False


def test_find_fresh_success_requires_newer_main_sha_and_same_job(monkeypatch):
    responses = [
        {
            "workflow_runs": [
                {
                    "id": 120,
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "b" * 40,
                },
                {
                    "id": 119,
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "a" * 40,
                },
            ]
        },
        {"jobs": [{"name": "repair", "conclusion": "success"}]},
    ]

    def fake_run_json(_args):
        return responses.pop(0)

    monkeypatch.setattr(reconcile, "_run_json", fake_run_json)
    evidence = reconcile.find_fresh_success(
        "owner/repo",
        {
            "workflow_id": 7,
            "run_id": 100,
            "head_sha": "a" * 40,
            "failed_job": "repair",
        },
    )
    assert evidence == {"run_id": 120, "head_sha": "b" * 40, "failed_job": "repair"}

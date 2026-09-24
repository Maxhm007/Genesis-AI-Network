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


def test_workflow_level_failure_requires_newer_successful_main_run(monkeypatch):
    responses = [
        {
            "workflow_runs": [
                {
                    "id": 130,
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "c" * 40,
                }
            ]
        }
    ]

    def fake_run_json(_args):
        return responses.pop(0)

    monkeypatch.setattr(reconcile, "_run_json", fake_run_json)
    evidence = reconcile.find_fresh_success(
        "owner/repo",
        {
            "workflow_id": 8,
            "run_id": 100,
            "head_sha": "a" * 40,
            "failed_job": "workflow",
        },
    )
    assert evidence == {"run_id": 130, "head_sha": "c" * 40, "failed_job": "workflow"}
    assert responses == []


def test_close_verified_tolerates_already_absent_lifecycle_labels(monkeypatch):
    calls = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args, **_kwargs):
        calls.append(args)
        if "--remove-label" in args and args[-1] == "genesis-action-autonomous":
            return Result(returncode=1, stderr="'genesis-action-autonomous' not found")
        return Result()

    monkeypatch.setattr(reconcile.subprocess, "run", fake_run)
    reconcile._close_verified(
        "owner/repo",
        909,
        {"run_id": 200, "head_sha": "b" * 40, "failed_job": "repair-and-promote"},
    )

    assert any("--add-label" in call and reconcile.SOLVED_LABEL in call for call in calls)
    assert any(call[:3] == ["gh", "issue", "close"] for call in calls)


def test_close_verified_creates_missing_solved_label_then_closes(monkeypatch):
    calls = []
    attempts = {"add": 0}

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args, **_kwargs):
        calls.append(args)
        if "--add-label" in args and reconcile.SOLVED_LABEL in args:
            attempts["add"] += 1
            if attempts["add"] == 1:
                return Result(returncode=1, stderr=f"'{reconcile.SOLVED_LABEL}' not found")
        return Result()

    monkeypatch.setattr(reconcile.subprocess, "run", fake_run)
    reconcile._close_verified(
        "owner/repo",
        910,
        {"run_id": 201, "head_sha": "c" * 40, "failed_job": "failover-next-issue"},
    )

    assert any(call[:3] == ["gh", "label", "create"] and reconcile.SOLVED_LABEL in call for call in calls)
    assert attempts["add"] == 2
    assert any(call[:3] == ["gh", "issue", "close"] for call in calls)

from scripts.action_failure_recovery import newer_successful_run


def test_newer_successful_main_run_marks_recovery():
    failed = {
        "id": 10,
        "created_at": "2026-09-19T10:00:00Z",
    }
    runs = [
        {
            "id": 11,
            "created_at": "2026-09-19T11:00:00Z",
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
        }
    ]
    recovered = newer_successful_run(failed, runs)
    assert recovered is not None
    assert recovered["id"] == 11


def test_failed_or_older_run_does_not_mark_recovery():
    failed = {
        "id": 10,
        "created_at": "2026-09-19T10:00:00Z",
    }
    runs = [
        {
            "id": 9,
            "created_at": "2026-09-19T09:00:00Z",
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
        },
        {
            "id": 11,
            "created_at": "2026-09-19T11:00:00Z",
            "head_branch": "main",
            "status": "completed",
            "conclusion": "failure",
        },
    ]
    assert newer_successful_run(failed, runs) is None


def test_non_main_success_does_not_mark_recovery():
    failed = {
        "id": 10,
        "created_at": "2026-09-19T10:00:00Z",
    }
    runs = [
        {
            "id": 11,
            "created_at": "2026-09-19T11:00:00Z",
            "head_branch": "feature",
            "status": "completed",
            "conclusion": "success",
        }
    ]
    assert newer_successful_run(failed, runs) is None

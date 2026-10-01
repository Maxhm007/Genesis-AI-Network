import scripts.genesis_teammate as module


def test_execution_task_key_is_stable_for_same_source_issue_across_runs():
    objective = "Autonomous Genesis development task from issue #867: observability work"
    assert module.execution_task_key(objective, "autonomous-867-run-a") == "source-issue-867"
    assert module.execution_task_key(objective, "autonomous-867-run-b") == "source-issue-867"


def test_execution_task_key_falls_back_to_comment_when_no_source_issue():
    assert module.execution_task_key("Owner requested a direct task", "comment-123") == "source-comment-comment-123"

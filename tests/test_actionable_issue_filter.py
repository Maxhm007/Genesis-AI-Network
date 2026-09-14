import scripts.agentic_lab_recovery_dispatch as module


def test_performance_indicator_title_is_non_actionable():
    issue = {
        "title": "[Performance Indicator] SWE-bench Pro score",
        "body": "- **Task type:** `capability_growth`\n- **Target:** `genesis/coding.py`\n",
    }
    assert module.actionable_issue(issue) is False


def test_frontier_benchmark_measurement_is_non_actionable():
    issue = {
        "title": "[Genesis Task] frontier benchmark measurement",
        "body": "- **Task type:** `frontier_benchmark_measurement`\n- **Target:** `genesis/benchmark_execution.py`\n",
    }
    assert module.actionable_issue(issue) is False


def test_performance_marker_is_non_actionable():
    issue = {
        "title": "Capability score history",
        "body": "<!-- genesis-performance-indicator -->\n- **Target:** `genesis/coding.py`\n",
    }
    assert module.actionable_issue(issue) is False


def test_concrete_repair_remains_actionable():
    issue = {
        "title": "[Genesis Task] repair issue solver timeout",
        "body": "- **Task type:** `self_repair`\n- **Target:** `genesis/coding.py`\n",
    }
    assert module.actionable_issue(issue) is True

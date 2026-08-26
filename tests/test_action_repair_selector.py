from scripts.action_failure_watchdog import encode_metadata
from scripts.action_repair_selector import choose_repairable_issue, classify_failure


def _issue(number: int, workflow_path: str, repair_cycles: int = 0, evidence: str = "") -> dict:
    marker = encode_metadata(
        {
            "workflow_id": 1,
            "workflow_name": "Example",
            "workflow_path": workflow_path,
            "run_id": 100 + number,
            "failed_job": "job",
            "failed_step": "step",
            "repair_cycles": repair_cycles,
        }
    )
    body = f"Sanitized failed-log evidence:\n{evidence}\n\n{marker}"
    return {"number": number, "body": body}


def test_selector_skips_owner_control_paths_and_exhausted_issues():
    issues = [
        _issue(10, ".github/workflows/action-repair-status.yml"),
        _issue(11, ".github/workflows/ordinary.yml", repair_cycles=3),
        _issue(12, ".github/workflows/repairable.yml", repair_cycles=1),
    ]
    assert choose_repairable_issue(issues) == 12


def test_selector_prefers_lowest_cycle_then_oldest_issue_within_same_class():
    issues = [
        _issue(30, ".github/workflows/a.yml", repair_cycles=1),
        _issue(20, ".github/workflows/b.yml", repair_cycles=0),
        _issue(15, ".github/workflows/c.yml", repair_cycles=0),
    ]
    assert choose_repairable_issue(issues) == 15


def test_classifier_recognizes_bounded_common_failure_classes():
    assert classify_failure("ModuleNotFoundError: No module named 'cryptography'") == "dependency"
    assert classify_failure("syntax error near unexpected token") == "syntax"
    assert classify_failure("artifact handoff file not found") == "artifact"
    assert classify_failure("AssertionError: expected 4") == "test"
    assert classify_failure("Name or service not known") == "infrastructure"


def test_selector_prioritizes_deterministic_failure_class_without_bypassing_guards():
    issues = [
        _issue(21, ".github/workflows/unknown.yml", evidence="unclassified failure"),
        _issue(22, ".github/workflows/dependency.yml", evidence="ModuleNotFoundError: No module named 'cryptography'"),
        _issue(23, ".github/workflows/syntax.yml", repair_cycles=1, evidence="syntax error near unexpected token"),
    ]
    assert choose_repairable_issue(issues) == 23

from scripts.action_failure_watchdog import encode_metadata
from scripts.action_repair_selector import choose_repairable_issue, classify_failure


def _issue(
    number: int,
    workflow_path: str,
    repair_cycles: int = 0,
    evidence: str = "",
    *,
    workflow_id: int = 1,
    failed_job: str = "job",
    failed_step: str = "step",
) -> dict:
    marker = encode_metadata(
        {
            "workflow_id": workflow_id,
            "workflow_name": "Example",
            "workflow_path": workflow_path,
            "run_id": 100 + number,
            "failed_job": failed_job,
            "failed_step": failed_step,
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


def test_selector_prefers_untouched_root_then_oldest_issue():
    issues = [
        _issue(15, ".github/workflows/a.yml", repair_cycles=1),
        _issue(30, ".github/workflows/b.yml", repair_cycles=0),
        _issue(20, ".github/workflows/c.yml", repair_cycles=0),
    ]
    assert choose_repairable_issue(issues) == 20


def test_classifier_recognizes_bounded_common_failure_classes():
    assert classify_failure("ModuleNotFoundError: No module named 'cryptography'") == "dependency"
    assert classify_failure("syntax error near unexpected token") == "syntax"
    assert classify_failure("artifact handoff file not found") == "artifact"
    assert classify_failure("AssertionError: expected 4") == "test"
    assert classify_failure("Name or service not known") == "infrastructure"


def test_newer_syntax_failure_does_not_jump_older_untouched_failure():
    issues = [
        _issue(21, ".github/workflows/unknown.yml", evidence="unclassified failure"),
        _issue(22, ".github/workflows/dependency.yml", evidence="ModuleNotFoundError: No module named 'cryptography'"),
        _issue(23, ".github/workflows/syntax.yml", evidence="syntax error near unexpected token"),
    ]
    assert choose_repairable_issue(issues) == 21


def test_retry_generation_rotates_behind_untouched_failure():
    issues = [
        _issue(40, ".github/workflows/older.yml", repair_cycles=1, evidence="syntax error"),
        _issue(41, ".github/workflows/newer.yml", repair_cycles=0, evidence="unclassified failure"),
    ]
    assert choose_repairable_issue(issues) == 41


def test_validator_a_b_duplicates_are_one_root_for_selection():
    issues = [
        _issue(
            50,
            ".github/workflows/validated.yml",
            workflow_id=8,
            failed_job="execute / validator_a",
            failed_step="Security review A",
        ),
        _issue(
            51,
            ".github/workflows/validated.yml",
            workflow_id=8,
            failed_job="execute / validator_b",
            failed_step="Security review B",
        ),
        _issue(52, ".github/workflows/other.yml", workflow_id=9),
    ]
    assert choose_repairable_issue(issues) == 50

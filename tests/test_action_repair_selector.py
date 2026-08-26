from scripts.action_failure_watchdog import encode_metadata
from scripts.action_repair_selector import choose_repairable_issue


def _issue(number: int, workflow_path: str, repair_cycles: int = 0) -> dict:
    body = encode_metadata(
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
    return {"number": number, "body": body}


def test_selector_skips_owner_control_paths_and_exhausted_issues():
    issues = [
        _issue(10, ".github/workflows/action-repair-status.yml"),
        _issue(11, ".github/workflows/ordinary.yml", repair_cycles=3),
        _issue(12, ".github/workflows/repairable.yml", repair_cycles=1),
    ]
    assert choose_repairable_issue(issues) == 12


def test_selector_prefers_lowest_cycle_then_oldest_issue():
    issues = [
        _issue(30, ".github/workflows/a.yml", repair_cycles=1),
        _issue(20, ".github/workflows/b.yml", repair_cycles=0),
        _issue(15, ".github/workflows/c.yml", repair_cycles=0),
    ]
    assert choose_repairable_issue(issues) == 15

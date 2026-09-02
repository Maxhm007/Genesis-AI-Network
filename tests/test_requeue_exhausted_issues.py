from pathlib import Path

from scripts.requeue_exhausted_issues import (
    ENGINE_PATHS,
    eligible_exhausted_issue,
    engine_generation,
    reset_attempt_status,
)


def _issue(body: str, labels: list[str], title: str = "[Genesis Task] repair") -> dict:
    return {
        "number": 42,
        "title": title,
        "body": body,
        "labels": [{"name": label} for label in labels],
    }


def test_engine_generation_is_stable_and_content_sensitive(tmp_path: Path):
    for relative in ENGINE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")

    first = engine_generation(tmp_path)
    second = engine_generation(tmp_path)
    assert first == second

    tracked = tmp_path / ENGINE_PATHS[0]
    tracked.write_text("changed", encoding="utf-8")
    assert engine_generation(tmp_path) != first


def test_only_exhausted_safe_target_issue_is_requeue_eligible(tmp_path: Path):
    target = tmp_path / "genesis/example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    body = "- **Target:** `genesis/example.py`\n\nFix the bounded defect."

    eligible, target_name = eligible_exhausted_issue(_issue(body, ["genesis-solver-exhausted"]), tmp_path)
    assert eligible is True
    assert target_name == "genesis/example.py"

    assert eligible_exhausted_issue(_issue(body, []), tmp_path)[0] is False
    assert eligible_exhausted_issue(_issue(body, ["genesis-solver-exhausted", "genesis-working"]), tmp_path)[0] is False


def test_measurement_and_protected_issues_are_not_requeued(tmp_path: Path):
    protected = tmp_path / "genesis/security.py"
    protected.parent.mkdir(parents=True)
    protected.write_text("VALUE = 1\n", encoding="utf-8")
    ordinary = tmp_path / "genesis/example.py"
    ordinary.write_text("VALUE = 1\n", encoding="utf-8")

    protected_body = "- **Target:** `genesis/security.py`"
    assert eligible_exhausted_issue(_issue(protected_body, ["genesis-solver-exhausted"]), tmp_path) == (False, "protected_target")

    measured_body = "- **Target:** `genesis/example.py`\nThe same comparable benchmark must show measured score improves."
    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (False, "measurement_lane")


def test_attempt_status_resets_for_new_engine_generation():
    oldest = "<!-- genesis-oldest-real-issue-solver -->\n<!-- genesis-solver-attempt:3 -->\nstate"
    priority = "<!-- genesis-priority-issue-solver -->\n<!-- genesis-priority-solver-attempt:2 -->\nstate"

    assert "genesis-solver-attempt:0" in reset_attempt_status(oldest)
    assert "genesis-priority-solver-attempt:0" in reset_attempt_status(priority)

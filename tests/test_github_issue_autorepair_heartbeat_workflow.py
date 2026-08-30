from pathlib import Path

from genesis.issue_worker_pool import select_issue_repair_batch
from scripts.reconcile_satisfied_issue import reconciliation_plan


SOLVER = Path(".github/workflows/genesis-oldest-issue-solver.yml")
WORKER = Path(".github/workflows/genesis-bounded-repair-worker.yml")


def _issue(number: int, *labels: str, title: str = "") -> dict:
    return {
        "number": number,
        "state": "OPEN",
        "updatedAt": f"2026-08-26T00:{number:02d}:00Z",
        "title": title,
        "labels": [{"name": label} for label in labels],
    }


def test_solver_is_the_only_queue_admission_lane_for_bounded_worker() -> None:
    solver = SOLVER.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")

    assert "genesis-bounded-repair-worker.yml" in solver
    assert "genesis-repair-in-progress" in solver
    assert "workflow_dispatch:" in worker
    assert "issue_number:" in worker
    assert "issues:" not in worker.split("on:", 1)[1].split("permissions:", 1)[0]


def test_worker_cannot_claim_arbitrary_unreserved_issue() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert 'index("genesis-repair-in-progress")' in text
    assert 'reserved=$(jq -r' in text
    assert 'if [[ "$state" != "OPEN" || "$reserved" != "true" ]]' in text


def test_shared_selector_excludes_non_generic_queue_records() -> None:
    rows = [
        _issue(24, "genesis-task", "duplicate"),
        _issue(25, "genesis-task", "genesis-persistent"),
        _issue(26, "genesis-task", "genesis-control"),
        _issue(27, "genesis-task", title="Genesis Control: persistent dashboard"),
        _issue(28, "genesis-task", title="[Genesis Self Improvement] specialist work"),
        _issue(29, "genesis-task", title="[Genesis Repair] repair the queue"),
    ]

    batch = select_issue_repair_batch(rows, max_parallel=1)

    assert batch.selected_issue_numbers == (29,)


def test_machine_generated_issue_can_reconcile_only_through_unique_grounding_test(tmp_path: Path) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "provider.py").write_text("STATE = 'ready'\n", encoding="utf-8")
    (tmp_path / "tests" / "test_provider.py").write_text(
        "def test_provider_requires_evidence():\n    assert True\n",
        encoding="utf-8",
    )
    issue = {
        "state": "OPEN",
        "title": "[Genesis Task] self repair — provider evidence",
        "labels": [{"name": "genesis-task"}, {"name": "genesis-autonomous"}],
        "body": (
            "- **Task type:** `self_repair`\n"
            "- **Source:** `genesis.issue_discovery`\n"
            "- **Target:** `genesis/provider.py`\n"
            "Grounding evidence: test_provider_requires_evidence\n"
        ),
    }

    plan = reconciliation_plan(issue, tmp_path)

    assert plan["eligible"] is True
    assert plan["node_id"] == "tests/test_provider.py::test_provider_requires_evidence"


def test_reconciliation_rejects_user_authored_or_ambiguous_evidence(tmp_path: Path) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "provider.py").write_text("STATE = 'ready'\n", encoding="utf-8")
    for name in ("test_one.py", "test_two.py"):
        (tmp_path / "tests" / name).write_text("def test_same():\n    assert True\n", encoding="utf-8")
    base = {
        "state": "OPEN",
        "labels": ["genesis-task", "genesis-autonomous"],
        "body": (
            "- **Task type:** `self_repair`\n"
            "- **Source:** `genesis.issue_discovery`\n"
            "- **Target:** `genesis/provider.py`\n"
            "Grounding evidence: test_same\n"
        ),
    }

    user_issue = dict(base, title="Please repair provider evidence")
    generated_issue = dict(base, title="[Genesis Task] self repair — provider evidence")

    assert reconciliation_plan(user_issue, tmp_path)["eligible"] is False
    assert reconciliation_plan(generated_issue, tmp_path)["eligible"] is False


def test_worker_closes_only_after_exact_post_promotion_tests_pass() -> None:
    text = WORKER.read_text(encoding="utf-8")

    promotion = text.index("Independently validate and promote exact candidate")
    reset = text.index("git reset --hard origin/main", promotion)
    full_test = text.index("python -m pytest -q", reset)
    close = text.index("state=closed", full_test)
    assert promotion < reset < full_test < close

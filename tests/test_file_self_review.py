from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from genesis.file_self_review import FileSelfReviewLoop, REVIEW_METHODS


class FakeProvider:
    name = "fake-review-provider"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def reason(self, prompt: str) -> str:
        assert self.responses, "unexpected provider call"
        return self.responses.pop(0)


def write_source(root: Path, name: str, body: str) -> str:
    path = root / "genesis" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path.relative_to(root).as_posix()


def test_reviews_smallest_file_first_and_advances_on_no_change(tmp_path: Path) -> None:
    small = write_source(tmp_path, "small.py", "VALUE = 1\n")
    write_source(tmp_path, "large.py", "VALUE = 1\n" * 20)
    loop = FileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: FakeProvider([
        '{"decision":"no_change","summary":"Already minimal and correct","objective":"","confidence":0.95}'
    ])

    assert loop.plan_next() is None
    status = loop.status()
    assert status["cursor"] == 1
    assert status["reviewed_count"] == 1
    state = loop._load()
    assert state["reviewed"][small]["status"] == "reviewed_no_change"
    lab_dirs = list((tmp_path / "runtime" / "task_reviews" / "file_self_review_lab").iterdir())
    assert len(lab_dirs) == 1
    assert (lab_dirs[0] / "original.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_improvement_is_planned_for_only_the_current_file(tmp_path: Path) -> None:
    target = write_source(tmp_path, "tiny.py", "def answer():\n    return 1\n")
    provider = FakeProvider([
        '{"decision":"improve","summary":"Return value is wrong for the documented helper","objective":"Return 2 instead of 1","confidence":0.9}',
        '{"edits":[{"path":"genesis/tiny.py","start_line":2,"end_line":2,"new":"    return 2"}]}'
    ])
    loop = FileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: provider

    plan = loop.plan_next()
    assert plan is not None
    assert set(plan["proposal"]["files"]) == {target}
    assert plan["proposal"]["files"][target] == "def answer():\n    return 2\n"
    assert plan["proposal"]["provenance"]["initiator"] == "genesis.file_self_review"
    assert plan["proposal"]["file_self_review"]["path"] == target

    lab = Path(loop._load()["current"]["lab"])
    assert (tmp_path / lab / "candidate.py").is_file()


def test_failed_candidate_keeps_same_file_and_changes_method(tmp_path: Path) -> None:
    target = write_source(tmp_path, "tiny.py", "def answer():\n    return 1\n")
    provider = FakeProvider([
        '{"decision":"improve","summary":"Use a safer return value","objective":"Return 2","confidence":0.8}',
        '{"edits":[{"path":"genesis/tiny.py","start_line":2,"end_line":2,"new":"    return 2"}]}'
    ])
    loop = FileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: provider
    plan = loop.plan_next()
    assert plan is not None

    loop.observe_execution(
        plan["proposal"],
        SimpleNamespace(
            tests_passed=False,
            committed=False,
            commit_sha=None,
            branch="genesis/candidate-failed",
            message="pytest failed",
        ),
    )
    current = loop._load()["current"]
    assert current["path"] == target
    assert current["status"] == "retry"
    assert current["method_index"] == 1
    assert current["attempts"] == 1
    assert "pytest failed" in current["last_error"]


def test_review_only_control_plane_is_not_autonomously_modified(tmp_path: Path) -> None:
    write_source(tmp_path, "autonomy_guard.py", "RULE = True\n")
    loop = FileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: FakeProvider([
        '{"decision":"improve","summary":"Potential guard simplification","objective":"Change guard","confidence":0.7}'
    ])

    assert loop.plan_next() is None
    state = loop._load()
    row = state["reviewed"]["genesis/autonomy_guard.py"]
    assert row["status"] == "reviewed_risk_escalation"
    assert row["owner_or_privileged_review_required"] is True


def test_method_sequence_is_bounded_and_explicit() -> None:
    assert len(REVIEW_METHODS) >= 5
    assert "fresh_independent_approach" in REVIEW_METHODS

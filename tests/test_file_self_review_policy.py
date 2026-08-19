from __future__ import annotations

from pathlib import Path

from genesis.file_self_review import REVIEW_METHODS
from genesis.file_self_review_policy import QuorumFileSelfReviewLoop


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


def test_single_no_change_does_not_advance_file(tmp_path: Path) -> None:
    target = write_source(tmp_path, "small.py", "VALUE = 1\n")
    loop = QuorumFileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: FakeProvider([
        '{"decision":"no_change","summary":"Looks correct","objective":"","confidence":0.9}'
    ])

    assert loop.plan_next() is None
    state = loop._load()
    assert state["cursor"] == 0
    assert state["current"]["path"] == target
    assert state["current"]["status"] == "retry"
    assert state["current"]["method_index"] == 1
    assert len(state["current"]["no_change_confirmations"]) == 1
    assert target not in state["reviewed"]


def test_two_distinct_no_change_methods_advance_file(tmp_path: Path) -> None:
    target = write_source(tmp_path, "small.py", "VALUE = 1\n")
    provider = FakeProvider([
        '{"decision":"no_change","summary":"Correct on edge cases","objective":"","confidence":0.9}',
        '{"decision":"no_change","summary":"Error handling is sufficient","objective":"","confidence":0.8}',
    ])
    loop = QuorumFileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: provider

    assert loop.plan_next() is None
    assert loop.plan_next() is None

    state = loop._load()
    assert state["cursor"] == 1
    assert state["current"] is None
    row = state["reviewed"][target]
    assert row["status"] == "reviewed_no_change"
    assert row["confirmation_count"] == 2
    assert row["confirmation_methods"] == list(REVIEW_METHODS[:2])


def test_improvement_finding_does_not_require_no_change_quorum(tmp_path: Path) -> None:
    target = write_source(tmp_path, "tiny.py", "def answer():\n    return 1\n")
    provider = FakeProvider([
        '{"decision":"improve","summary":"Wrong return value","objective":"Return 2","confidence":0.95}',
        '{"edits":[{"path":"genesis/tiny.py","start_line":2,"end_line":2,"new":"    return 2"}]}'
    ])
    loop = QuorumFileSelfReviewLoop(tmp_path)
    loop.coding._provider = lambda: provider

    plan = loop.plan_next()
    assert plan is not None
    assert set(plan["proposal"]["files"]) == {target}

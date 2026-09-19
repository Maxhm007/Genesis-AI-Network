from __future__ import annotations

import pytest

from genesis.learned_capabilities import run_capability


PLAN = [
    {"id": "search", "tool": "search", "args": {"query": "topic"}},
    {"id": "read", "tool": "read", "args": {"source": "result"}, "depends_on": ["search"]},
    {"id": "verify", "tool": "verify", "args": {}, "depends_on": ["read"]},
]


def test_tool_call_planning_selects_first_ready_step():
    result = run_capability(
        "tool_call_planning",
        PLAN,
        allowed_tools={"search", "read", "verify"},
    )
    assert result["action"] == "execute"
    assert result["next_step"]["id"] == "search"


def test_tool_call_planning_advances_after_verified_results():
    result = run_capability(
        "tool_call_planning",
        PLAN,
        allowed_tools={"search", "read", "verify"},
        results={"search": {"ok": True, "output": "r1"}},
    )
    assert result["action"] == "execute"
    assert result["next_step"]["id"] == "read"
    assert result["completed_steps"] == ("search",)


def test_tool_call_planning_requires_revision_after_failure():
    result = run_capability(
        "tool_call_planning",
        PLAN,
        results={"search": {"ok": False, "error": "timeout"}},
    )
    assert result["action"] == "revise"
    assert result["failed_step"] == "search"


def test_tool_call_planning_reports_complete():
    result = run_capability(
        "tool_call_planning",
        PLAN,
        results={
            "search": {"ok": True},
            "read": {"ok": True},
            "verify": {"ok": True},
        },
    )
    assert result["action"] == "complete"
    assert result["remaining_steps"] == ()


def test_tool_call_planning_rejects_unapproved_tool():
    with pytest.raises(ValueError, match="tool is not allowed"):
        run_capability(
            "tool_call_planning",
            PLAN,
            allowed_tools={"search", "read"},
        )


def test_tool_call_planning_rejects_cycles_unknown_dependencies_and_bad_results():
    cyclic = [
        {"id": "a", "tool": "x", "depends_on": ["b"]},
        {"id": "b", "tool": "y", "depends_on": ["a"]},
    ]
    with pytest.raises(ValueError, match="dependency cycle"):
        run_capability("tool_call_planning", cyclic)

    with pytest.raises(ValueError, match="unknown dependency"):
        run_capability(
            "tool_call_planning",
            [{"id": "a", "tool": "x", "depends_on": ["missing"]}],
        )

    with pytest.raises(ValueError, match="boolean ok"):
        run_capability(
            "tool_call_planning",
            [{"id": "a", "tool": "x"}],
            results={"a": {"ok": "yes"}},
        )


def test_tool_call_planning_enforces_step_bound():
    steps = [{"id": f"s{i}", "tool": "x"} for i in range(4)]
    with pytest.raises(ValueError, match="step bound"):
        run_capability("tool_call_planning", steps, max_steps=3)

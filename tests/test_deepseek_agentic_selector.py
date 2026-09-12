from scripts.deepseek_agentic_selector import score, select, target_from


def issue(number, title, body, labels=None):
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": name} for name in (labels or [])],
    }


def test_extracts_markdown_target():
    row = issue(1, "Repair", "- **Target:** `genesis/task_router.py`\n### Acceptance\nTests pass")
    assert target_from(row) == "genesis/task_router.py"


def test_rejects_protected_target():
    row = issue(2, "Repair", "Target: `genesis/security.py`\nAcceptance: tests pass")
    value, detail = score(row)
    assert value < 0
    assert detail["reason"] == "no_safe_explicit_python_target"


def test_does_not_compete_with_active_solver():
    row = issue(
        3,
        "Fix failing parser test",
        "Target: `genesis/task_router.py`\nAcceptance: regression test passes",
        ["genesis-repair-in-progress"],
    )
    value, detail = score(row)
    assert value < 0
    assert detail["reason"] == "conflicting_or_unsuitable_label"


def test_prefers_clear_repair_over_vague_upgrade():
    repair = issue(
        10,
        "Fix incorrect routing failure",
        "Target: `genesis/task_router.py`\nAcceptance: regression test and full pytest pass",
    )
    upgrade = issue(
        9,
        "Self upgrade",
        "Target: `genesis/learned_capabilities.py`\nAcceptance: capability exists",
    )
    chosen = select([upgrade, repair])
    assert chosen is not None
    assert chosen["number"] == 10


def test_returns_none_when_no_issue_is_safe():
    rows = [
        issue(20, "Human task", "Target: `genesis/task_router.py`", ["genesis-needs-human"]),
        issue(21, "Protected", "Target: `genesis/security.py`"),
    ]
    assert select(rows) is None

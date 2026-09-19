from genesis.anti_stuck import Attempt, attempt_marker, state_marker
from scripts.deepseek_agentic_selector import plan_deepseek_attempt, score, select, target_from


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


def test_deepseek_attempt_plan_rotates_without_repeating_same_epoch():
    row = issue(
        30,
        "Repair parser",
        "- **Target:** `genesis/learned_capabilities.py`\n### Acceptance\nTests pass",
    )
    first = plan_deepseek_attempt(row, [], "genesis/learned_capabilities.py")
    assert first["eligible"] is True
    assert first["strategy"] == "evidence_first"

    comments = [
        {"body": state_marker(first["state_token"])},
        {"body": first["attempt_marker"] + "\n<!-- genesis-deepseek-attempt:1 -->"},
        {"body": "<!-- genesis-deepseek-result:retry -->\nrepair status: `repair_failed_validation`"},
    ]
    second = plan_deepseek_attempt(row, comments, "genesis/learned_capabilities.py")
    assert second["eligible"] is True
    assert second["strategy"] == "alternative_implementation"


def test_deepseek_attempt_plan_exhausts_three_strategies_per_material_state():
    row = issue(
        31,
        "Repair parser",
        "- **Target:** `genesis/learned_capabilities.py`\n### Acceptance\nTests pass",
    )
    initial = plan_deepseek_attempt(row, [], "genesis/learned_capabilities.py")
    token = initial["state_token"]
    comments = [{"body": state_marker(token)}]
    for index, strategy in enumerate(
        ("evidence_first", "alternative_implementation", "diagnostic_reframe"),
        start=1,
    ):
        comments.append(
            {
                "body": attempt_marker(
                    Attempt(
                        strategy,
                        "deepseek",
                        "Gene 003",
                        "genesis/learned_capabilities.py",
                    )
                )
                + f"\n<!-- genesis-deepseek-attempt:{index} -->"
            }
        )
        comments.append(
            {"body": "<!-- genesis-deepseek-result:retry -->\nrepair status: `repair_failed_validation`"}
        )

    result = plan_deepseek_attempt(row, comments, "genesis/learned_capabilities.py")
    assert result["eligible"] is False
    assert result["reason"] == "deepseek_strategy_epoch_exhausted"


def test_deepseek_rejects_blocked_issue():
    row = issue(
        32,
        "Repair",
        "Target: `genesis/task_router.py`",
        ["genesis-blocked"],
    )
    value, detail = score(row)
    assert value < 0
    assert detail["reason"] == "conflicting_or_unsuitable_label"

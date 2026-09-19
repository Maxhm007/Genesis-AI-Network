from __future__ import annotations

from pathlib import Path

from genesis.anti_stuck import (
    Attempt,
    anti_stuck_decision,
    attempt_history,
    attempt_marker,
    current_epoch_comments,
    material_state_token,
    materially_equivalent_attempt,
    next_lane_strategy,
    should_release_worker,
    state_marker,
)


def test_repeated_material_attempt_is_rejected():
    history = (
        Attempt(
            strategy="evidence_first",
            provider="agentic-default",
            gene="Gene 0",
            target="genesis/example.py",
            blocker="repair_failed_validation",
            result="repair_failed_validation",
        ),
    )
    candidate = Attempt(
        strategy="evidence_first",
        provider="agentic-default",
        gene="Gene 0",
        target="genesis/example.py",
        blocker="repair_failed_validation",
    )
    assert materially_equivalent_attempt(history, candidate) is True


def test_provider_switch_after_distinct_failures():
    history = (
        Attempt("evidence_first", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("alternative_implementation", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
    )
    decision = anti_stuck_decision(history)
    assert decision.action == "switch_lane"
    assert decision.provider == "qwen3"
    assert decision.gene == "Gene 0"


def test_gene_switch_reaches_deepseek_after_qwen3_failure():
    history = (
        Attempt("evidence_first", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("alternative_implementation", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("qwen3_fallback", "qwen3", "Gene 0", "genesis/example.py", result="failed"),
    )
    decision = anti_stuck_decision(history)
    assert decision.action == "switch_lane"
    assert decision.provider == "deepseek"
    assert decision.gene == "Gene 003"


def test_further_distinct_failure_requests_capability_blocker():
    history = (
        Attempt("evidence_first", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("alternative_implementation", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("qwen3_fallback", "qwen3", "Gene 0", "genesis/example.py", result="failed"),
        Attempt("evidence_first", "deepseek", "Gene 003", "genesis/example.py", result="failed"),
        Attempt("diagnostic_reframe", "agentic-default", "Gene 0", "genesis/example.py", result="failed"),
    )
    decision = anti_stuck_decision(history)
    assert decision.action == "capability"


def test_next_lane_strategy_never_repeats_in_same_epoch():
    history = (
        Attempt("evidence_first", "deepseek", "Gene 003", "genesis/example.py", result="failed"),
        Attempt("alternative_implementation", "deepseek", "Gene 003", "genesis/example.py", result="failed"),
    )
    assert next_lane_strategy(
        history,
        provider="deepseek",
        gene="Gene 003",
        target="genesis/example.py",
        strategies=("evidence_first", "alternative_implementation", "diagnostic_reframe"),
    ) == "diagnostic_reframe"


def test_first_epoch_preserves_legacy_history_then_marker_scopes_it():
    legacy = [
        {"body": "<!-- genesis-agentic-strategy:evidence_first -->"},
        {"body": "<!-- genesis-agentic-strategy-result:evidence_first --> repair status: `failed`"},
    ]
    history = attempt_history(legacy, "abc", "genesis/example.py")
    assert [row.strategy for row in history] == ["evidence_first"]

    scoped = [
        *legacy,
        {"body": state_marker("abc")},
        {"body": attempt_marker(Attempt("alternative_implementation", "agentic-default", "Gene 0", "genesis/example.py"))},
        {"body": "<!-- genesis-agentic-strategy-result:alternative_implementation --> repair status: `failed`"},
    ]
    history = attempt_history(scoped, "abc", "genesis/example.py")
    assert [row.strategy for row in history] == ["alternative_implementation"]


def test_material_state_change_resets_attempt_epoch(tmp_path: Path):
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("value = 1\n", encoding="utf-8")
    issue = {"body": "same evidence"}
    old = material_state_token(issue, "genesis/example.py", [], root=tmp_path)
    comments = [
        {"body": state_marker(old)},
        {"body": attempt_marker(Attempt("evidence_first", "agentic-default", "Gene 0", "genesis/example.py"))},
    ]

    target.write_text("value = 2\n", encoding="utf-8")
    new = material_state_token(issue, "genesis/example.py", comments, root=tmp_path)

    assert new != old
    assert current_epoch_comments(comments, new) == []
    assert attempt_history(comments, new, "genesis/example.py") == ()


def test_capability_release_changes_material_state(tmp_path: Path):
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("value = 1\n", encoding="utf-8")
    issue = {"body": "evidence"}

    before = material_state_token(issue, "genesis/example.py", [], root=tmp_path)
    after = material_state_token(
        issue,
        "genesis/example.py",
        [{"body": "<!-- genesis-agentic-capability-release:99 -->"}],
        root=tmp_path,
    )
    assert before != after


def test_waiting_capability_releases_worker_capacity():
    assert should_release_worker(["genesis-task", "genesis-waiting-capability"]) is True
    assert should_release_worker(["genesis-task", "genesis-autonomous"]) is False

import scripts.agentic_lab_recovery_dispatch as module


def test_agentic_strategy_order_is_materially_distinct_and_dependency_last() -> None:
    assert module.STRATEGIES == (
        "evidence_first",
        "alternative_implementation",
        "diagnostic_reframe",
        "dependency_diagnosis",
    )

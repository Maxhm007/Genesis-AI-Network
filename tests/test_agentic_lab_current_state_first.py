from pathlib import Path


def test_recovery_solver_starts_with_evidence_first_and_requires_authorization():
    source = Path("scripts/recovery_solver_dispatch.py").read_text(encoding="utf-8")
    assert 'RECOVERY_STRATEGIES = (\n    "evidence_first",' in source
    assert '"genesis-autonomous",\n                    AGENTIC_LABEL' in source
    assert 'or "genesis-autonomous" not in fresh_labels' in source


def test_agentic_strategy_guidance_requires_current_main_check_before_editing():
    source = Path("scripts/agentic_strategy_repair.py").read_text(encoding="utf-8")
    assert "Before proposing ANY edit, inspect current main" in source
    assert "If it is already satisfied, do not invent or replay a patch" in source
    assert 'evidence["current_state_checked_first"] = True' in source

import math

import pytest

from genesis.learned_capabilities import run_capability, validate_registry


def test_issue_427_martingale_information_budget_keeps_step_evidence_and_peeking_penalty():
    result = run_capability(
        "martingale_information_budget_427",
        [0.1, 0.2, 0.05],
        peeking_penalty=0.07,
    )
    assert result["steps"] == 3
    assert math.isclose(result["conditional_divergence"], 0.35)
    assert math.isclose(result["peeking_penalty"], 0.07)
    assert math.isclose(result["information_budget"], 0.42)


def test_issue_431_lfm2_tensor_split_is_bounded_and_normalized():
    result = run_capability("lfm2_tensor_split_plan_431", "LFM2MOE", [8, 4, 4])
    assert result == pytest.approx((0.5, 0.25, 0.25))
    with pytest.raises(ValueError):
        run_capability("lfm2_tensor_split_plan_431", "other", [1, 1])


def test_issue_432_partial_k_extent_never_reads_past_remaining_k():
    assert run_capability("partial_k_tile_extent_432", 70, 0) == 32
    assert run_capability("partial_k_tile_extent_432", 70, 32) == 32
    assert run_capability("partial_k_tile_extent_432", 70, 64) == 6
    assert run_capability("partial_k_tile_extent_432", 70, 70) == 0


def test_issue_433_mmproj_device_selection_preserves_explicit_then_legacy_fallback():
    available = ["cpu", "cuda:0", "cuda:1"]
    assert run_capability("mmproj_device_selection_433", "cuda:1", "cuda:0", available) == "cuda:1"
    assert run_capability("mmproj_device_selection_433", None, "cuda:0", available) == "cuda:0"
    assert run_capability("mmproj_device_selection_433", None, None, available, default="cpu") == "cpu"
    assert validate_registry() is True

def test_issue_427_rejects_aggregate_float_overflow():
    with pytest.raises(ValueError, match="finite bounds"):
        run_capability("martingale_information_budget_427", [1e308, 1e308])


def test_issue_431_rejects_weight_sum_overflow():
    with pytest.raises(ValueError, match="positive finite"):
        run_capability("lfm2_tensor_split_plan_431", "LFM2", [1e308, 1e308])


def test_issue_433_bounds_available_device_scan():
    with pytest.raises(ValueError, match="scan exceeds bound"):
        run_capability("mmproj_device_selection_433", None, None, ["cpu"] * 65)

def test_issue_427_bounds_iterator_consumption():
    def values():
        while True:
            yield 0.01
    with pytest.raises(ValueError, match="bounded input size"):
        run_capability("martingale_information_budget_427", values())


def test_issue_431_bounds_weight_iterator_consumption():
    def weights():
        while True:
            yield 1.0
    with pytest.raises(ValueError, match="bounded input size"):
        run_capability("lfm2_tensor_split_plan_431", "LFM2", weights())


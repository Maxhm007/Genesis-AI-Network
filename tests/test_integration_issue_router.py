from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/genesis-integration-issue-router.yml"


def test_integration_router_targets_benchmark_and_integration_work() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "benchmark_runner_integration" in text
    assert "genesis/benchmark_execution.py" in text
    assert "integration_sensitive" in text
    assert "genesis-integration-route" in text


def test_integration_router_preserves_validation_boundaries() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "do not reorder unrelated context" in text
    assert "full repository suite before promotion" in text
    assert "protected-file boundaries" in text
    assert "verified closure remain mandatory" in text


def test_integration_router_wakes_existing_controller_without_new_close_lane() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gh workflow run genesis-sequential-issue-controller.yml" in text
    assert "state=closed" not in text
    assert "state_reason" not in text

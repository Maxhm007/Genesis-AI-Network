from pathlib import Path

def test_cpu_workflow_is_bounded_and_non_deploying():
    text = Path(".github/workflows/genesis-cpu-training.yml").read_text()
    assert "timeout-minutes: 25" in text
    assert "permissions:\n  contents: read" in text
    assert "holdout_ready" in text
    assert "steps.readiness.outputs.ready == 'true'" in text
    assert "run_genesis_cpu_experiment" in text

def test_cpu_experiment_uses_model_lab_and_holdout():
    text = Path("scripts/run_genesis_cpu_experiment.py").read_text()
    assert "ModelTrainingLane" in text
    assert 'device="cpu"' in text
    assert "baseline_holdout_loss" in text
    assert "trained_holdout_loss" in text
    assert '"automatic_activation": False' in text

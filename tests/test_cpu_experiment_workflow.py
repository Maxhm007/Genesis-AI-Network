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

def test_readiness_shell_python_expression(tmp_path):
    import json
    import subprocess
    import sys
    path = tmp_path / "readiness.json"
    path.write_text(json.dumps({"status": "holdout_ready"}))
    cmd = 'import json,sys; print(json.load(open(sys.argv[1]))["status"])'
    run = subprocess.run([sys.executable, "-c", cmd, str(path)], capture_output=True, text=True, check=True)
    assert run.stdout.strip() == "holdout_ready"


def test_base_model_revision_is_immutable_and_used_for_download():
    import ast
    source = Path("scripts/run_genesis_cpu_experiment.py").read_text()
    ast.parse(source)
    assert 'MODEL_REVISION = "93efa2f097d58c2a74874c7e644dbc9b0cee75a2"' in source
    assert "revision=MODEL_REVISION" in source
    assert '"base_model_revision": MODEL_REVISION' in source

"""Regression guard: regular Gene Pulse must publish learning feedback and metrics."""
from pathlib import Path


def test_gene_pulse_reports_learning_and_adaptive_feedback():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "gene_pulse_core.py").read_text()
    assert 'result["learning_evolution"] = learning' in source
    assert 'result["adaptive_feedback"] = AdaptiveLearningEngine(ROOT).run_once()' in source
    assert 'result["learning_metrics"] = learning_metrics(' in source


def test_gene_pulse_workflow_persists_learning_evidence():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/gene-pulse.yml").read_text()
    assert 'python scripts/gene_pulse.py --gene "$GENE_ID"' in workflow
    assert "runtime/learning_preferences.json" in workflow
    assert "runtime/evolution/upgrade_process.json" in workflow
    assert "tests/test_gene_pulse_learning_alignment.py" in workflow

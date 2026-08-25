from pathlib import Path


def test_coding_pulse_returns_to_gene_only_when_chain_decision_dispatches() -> None:
    workflow = Path(".github/workflows/coding-intelligence-pulse.yml").read_text(encoding="utf-8")

    assert "- name: Return to normal Gene Pulse" in workflow
    assert "if: env.CONTINUE_CHAIN == 'true' && steps.pulse.outputs.dispatch_next == 'true'" in workflow

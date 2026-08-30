from pathlib import Path


WORKFLOW = Path('.github/workflows/gene-pulse.yml')


def test_gene_pulse_yields_to_proactive_specialist_handoff() -> None:
    text = WORKFLOW.read_text(encoding='utf-8')

    read_step = text.split('- name: Read pulse and specialist handoffs', 1)[1].split('- name: Push isolated candidate to review queue', 1)[0]
    assert "github_terminal_reconcile_before" in read_step
    assert "awaiting_specialist_replacement" in read_step
    assert "specialist_handoff=true" in read_step

    assert '- name: Yield next slot to Proactive Development' in text
    assert 'gh workflow run proactive-development.yml --ref main' in text

    request_step = text.split('- name: Request next pulse', 1)[1]
    assert "steps.pulse.outputs.specialist_handoff != 'true'" in request_step

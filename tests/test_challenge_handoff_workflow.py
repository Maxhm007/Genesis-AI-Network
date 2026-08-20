from pathlib import Path


def test_challenge_assignment_does_not_directly_trigger_file_review():
    workflow = Path('.github/workflows/file-self-review.yml').read_text(encoding='utf-8')
    assert "- 'config/genesis_challenge.json'" not in workflow
    assert 'workflow_call:' in workflow


def test_validated_quorum_handoff_remains_the_challenge_entrypoint():
    workflow = Path('.github/workflows/independent-validator-gate.yml').read_text(encoding='utf-8')
    assert "grep -Fxq 'config/genesis_challenge.json'" in workflow
    assert "needs: quorum_gate" in workflow
    assert "uses: ./.github/workflows/file-self-review.yml" in workflow
    assert "permissions:\n      contents: write" in workflow

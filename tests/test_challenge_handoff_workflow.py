from pathlib import Path


def test_challenge_assignment_does_not_directly_trigger_file_review():
    workflow = Path('.github/workflows/file-self-review.yml').read_text(encoding='utf-8')
    trigger_block = workflow.split('\npermissions:', 1)[0]
    assert 'push:' not in trigger_block
    assert 'workflow_call:' in trigger_block
    assert 'workflow_dispatch:' in trigger_block
    assert 'schedule:' in trigger_block


def test_file_review_reports_handoff_before_runtime_setup():
    workflow = Path('.github/workflows/file-self-review.yml').read_text(encoding='utf-8')
    handoff = workflow.index('Publish challenge handoff entered stage')
    runtime_cache = workflow.index('Restore shared Genesis runtime state')
    reasoning_cache = workflow.index('Restore reasoning caches')
    install_runtime = workflow.index('Install local reasoning runtime')
    assert handoff < runtime_cache < reasoning_cache < install_runtime
    assert '--stage handoff_entered' in workflow
    assert 'genesis/challenge-diagnostics-v5' in workflow


def test_validated_quorum_handoff_remains_the_challenge_entrypoint():
    workflow = Path('.github/workflows/independent-validator-gate.yml').read_text(encoding='utf-8')
    assert "grep -Fxq 'config/genesis_challenge.json'" in workflow
    assert 'needs: quorum_gate' in workflow
    assert 'uses: ./.github/workflows/file-self-review.yml' in workflow
    assert "permissions:\n      contents: write" in workflow

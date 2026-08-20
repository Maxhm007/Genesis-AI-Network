from pathlib import Path


def test_challenge_assignment_does_not_directly_trigger_file_review():
    workflow = Path('.github/workflows/file-self-review.yml').read_text(encoding='utf-8')
    trigger_block = workflow.split('\npermissions:', 1)[0]
    assert 'push:' not in trigger_block
    assert 'workflow_call:' in trigger_block
    assert 'workflow_dispatch:' in trigger_block
    assert 'schedule:' in trigger_block


def test_file_review_separates_intrinsic_schedule_from_assigned_challenge_mode():
    workflow = Path('.github/workflows/file-self-review.yml').read_text(encoding='utf-8')
    assert 'run_assigned_challenge:' in workflow
    assert 'default: false' in workflow
    assert 'GENESIS_RUN_ASSIGNED_CHALLENGE: ${{ inputs.run_assigned_challenge == true }}' in workflow

    validator = Path('.github/workflows/independent-validator-gate.yml').read_text(encoding='utf-8')
    assert 'uses: ./.github/workflows/file-self-review.yml' in validator
    assert 'with:\n      run_assigned_challenge: true' in validator


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
    assert 'run_assigned_challenge: true' in workflow


def test_validator_schedule_recovers_any_still_active_challenge():
    workflow = Path('.github/workflows/independent-validator-gate.yml').read_text(encoding='utf-8')
    assert "github.event_name == 'schedule'" in workflow
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert 'if [[ "${{ github.event_name }}" != "schedule" ]]; then' in workflow
    assert "git diff --name-only HEAD^ HEAD | grep -Fxq 'config/genesis_challenge.json'" in workflow
    assert "get('status', 'active')" in workflow

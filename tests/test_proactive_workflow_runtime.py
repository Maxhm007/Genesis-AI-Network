from pathlib import Path


def test_proactive_workflow_allows_local_reasoning_to_finish():
    workflow = Path('.github/workflows/proactive-development.yml').read_text(encoding='utf-8')
    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS: '180'" in workflow
    assert 'timeout-minutes: 35' in workflow

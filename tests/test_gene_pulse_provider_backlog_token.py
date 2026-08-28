from pathlib import Path


WORKFLOW = Path(".github/workflows/gene-pulse.yml")


def test_provider_backlog_inspection_receives_github_token_without_permission_widening() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    step = text.split("- name: Detect provider-bound coding work", 1)[1].split("- name: Configure Genesis Git identity", 1)[0]
    assert "id: provider_gate" in step
    assert "env:" in step
    assert "GITHUB_TOKEN: ${{ github.token }}" in step
    assert 'python scripts/pulse_provider_recovery.py inspect --github-output "$GITHUB_OUTPUT"' in step

    permissions = text.split("permissions:", 1)[1].split("concurrency:", 1)[0]
    assert "contents: write" in permissions
    assert "actions: write" in permissions
    assert "issues: write" in permissions
    assert "pull-requests:" not in permissions
    assert "checks:" not in permissions

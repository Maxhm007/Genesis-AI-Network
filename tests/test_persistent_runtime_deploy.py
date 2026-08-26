from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_external_persistent_deploy_workflow_is_retired():
    assert not (WORKFLOWS / "deploy-persistent-runtime.yml").exists()


def test_no_active_workflow_requires_external_runtime_host_or_ssh_secrets():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOWS.glob("*.yml"))
    )
    for forbidden in (
        "GENE_RUNTIME_HOST",
        "GENE_RUNTIME_USER",
        "GENE_RUNTIME_SSH_KEY",
        "GENE_RUNTIME_HOST_KEY",
    ):
        assert forbidden not in text


def test_gene_pulse_is_issue_authoritative_and_persists_actions_state():
    text = (WORKFLOWS / "gene-pulse.yml").read_text(encoding="utf-8")
    assert "issues: write" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "actions/cache/restore@v4" in text
    assert "actions/cache/save@v4" in text
    assert "runtime/genesis_tasks.sqlite3" in text
    assert "gh workflow run gene-pulse.yml" in text


def test_coding_pulse_keeps_issue_authority_when_provider_is_needed():
    text = (WORKFLOWS / "coding-intelligence-pulse.yml").read_text(encoding="utf-8")
    assert "issues: write" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "python scripts/gene_pulse.py" in text
    assert "python scripts/benchmark_task_worker.py" in text


def test_actions_heartbeat_recovers_continuous_runtime_every_fifteen_minutes():
    text = (WORKFLOWS / "autonomy-heartbeat.yml").read_text(encoding="utf-8")
    assert 'cron: "*/15 * * * *"' in text
    assert "gh workflow run gene-pulse.yml" in text
    assert "cancel-in-progress: false" in text
    assert "GitHub Actions is the production continuous runtime" in text

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_systemd_service_runs_issue_authoritative_gene_and_restarts():
    text = (ROOT / "deploy" / "systemd" / "gene-continuous@.service").read_text(encoding="utf-8")
    assert "-m scripts.gene_issue_continuous --gene %i" in text
    assert "EnvironmentFile=-/etc/genesis/github.env" in text
    assert "GITHUB_REPOSITORY=Maxhm007/Genesis-AI-Network" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text


def test_installer_requires_issue_credential_and_restarts_gene_service():
    text = (ROOT / "deploy" / "install_persistent_runtime.sh").read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in text
    assert "/etc/genesis/github.env" in text
    assert "systemctl enable" in text
    assert "systemctl restart" in text
    assert "cron" not in text.lower()
    assert "gene-node-1" in text


def test_deploy_workflow_requires_runtime_issue_token_and_pinned_host_key():
    text = (ROOT / ".github" / "workflows" / "deploy-persistent-runtime.yml").read_text(encoding="utf-8")
    assert "GENE_RUNTIME_ENABLED" in text
    assert "GENE_RUNTIME_HOST_KEY" in text
    assert "GENE_RUNTIME_GITHUB_TOKEN" in text
    assert "Provision GitHub Issue authority credential" in text
    assert "ssh-keyscan" not in text
    assert "systemctl is-active" in text

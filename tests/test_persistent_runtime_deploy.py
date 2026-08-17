from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_systemd_service_runs_continuous_gene_and_restarts():
    text = (ROOT / "deploy" / "systemd" / "gene-continuous@.service").read_text(encoding="utf-8")
    assert "scripts/gene_continuous_work.py --gene %i" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text


def test_installer_enables_gene_service_without_cron():
    text = (ROOT / "deploy" / "install_persistent_runtime.sh").read_text(encoding="utf-8")
    assert "systemctl enable --now" in text
    assert "cron" not in text.lower()
    assert "gene-node-1" in text


def test_deploy_workflow_requires_explicit_runtime_enablement_and_pinned_host_key():
    text = (ROOT / ".github" / "workflows" / "deploy-persistent-runtime.yml").read_text(encoding="utf-8")
    assert "GENE_RUNTIME_ENABLED" in text
    assert "GENE_RUNTIME_HOST_KEY" in text
    assert "ssh-keyscan" not in text
    assert "systemctl is-active" in text

from pathlib import Path

from genesis.security import SecurityModule


def test_security_module_detects_missing_identity(tmp_path: Path):
    report = SecurityModule(tmp_path).inspect()
    assert report.status == "findings"
    assert any(item.finding_id == "protected-identity-missing" for item in report.findings)


def test_security_module_clean_minimal_repo(tmp_path: Path, monkeypatch):
    (tmp_path / "GENESIS_CONSTITUTION.md").write_text("constitution\n", encoding="utf-8")
    (tmp_path / "GENESIS_BLOCK.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "secret_guard.py").write_text("# guard\n", encoding="utf-8")
    module = SecurityModule(tmp_path)
    monkeypatch.setattr(module, "_tracked_files", lambda: ["GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"])
    report = module.inspect()
    assert report.status == "pass"
    assert report.checks["no_tracked_sensitive_files"] is True


def test_security_module_flags_tracked_private_key(tmp_path: Path, monkeypatch):
    (tmp_path / "GENESIS_CONSTITUTION.md").write_text("constitution\n", encoding="utf-8")
    (tmp_path / "GENESIS_BLOCK.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "secret_guard.py").write_text("# guard\n", encoding="utf-8")
    module = SecurityModule(tmp_path)
    monkeypatch.setattr(module, "_tracked_files", lambda: ["state/node_identity.key"])
    report = module.inspect()
    assert any(item.finding_id == "tracked-sensitive-file" for item in report.findings)

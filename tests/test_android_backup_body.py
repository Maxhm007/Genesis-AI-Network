from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_backup_body_policy_keeps_pulses_primary():
    policy = json.loads((ROOT / "config" / "android_backup_body.json").read_text(encoding="utf-8"))
    assert policy["identity"] == "Genesis"
    assert policy["role"] == "backup_body_runtime"
    assert policy["creates_new_gene"] is False
    assert policy["primary_continuity"] == "gene_pulse_network"
    assert policy["principles"]["pulses_remain_primary"] is True
    assert policy["principles"]["one_issue_focus_remains_required"] is True


def test_android_client_has_private_backup_snapshot_controls():
    source = (ROOT / "mobile" / "app" / "src" / "main" / "java" / "org" / "genesisai" / "mobile" / "MainActivity.java").read_text(encoding="utf-8")
    assert 'SNAPSHOT_FILE = "genesis_backup_state.json"' in source
    assert 'openFileOutput(filename, MODE_PRIVATE)' in source
    assert 'writePrivateJson(SNAPSHOT_FILE, json)' in source
    assert '"/v1/owner/dashboard"' in source
    assert 'backup_body_armed' in source
    assert 'Bearer token (not stored)' in source
    assert 'putString("base_url"' in source
    assert 'putString("token"' not in source


def test_backup_body_docs_describe_bounded_phase2_executor():
    text = (ROOT / "docs" / "ANDROID_BACKUP_BODY.md").read_text(encoding="utf-8")
    assert "not a new Gene" in text
    assert "Gene Pulse Network" in text
    phase2 = (ROOT / "docs" / "GENESIS_ANDROID_EMERGENCY_PULSES.md").read_text(encoding="utf-8")
    assert "bounded Android-native emergency pulse engine" in phase2
    assert "not a full offline replacement" in phase2

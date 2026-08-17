from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_emergency_pulse_is_candidate_only_and_single_step():
    engine = (ROOT / "mobile/app/src/main/java/org/genesisai/mobile/EmergencyPulseEngine.java").read_text(encoding="utf-8")
    assert 'result.put("candidate_only", true)' in engine
    assert 'result.put("canonical_mutation_allowed", false)' in engine
    assert 'result.put("requires_network_validation", true)' in engine
    assert 'result.put("action", "continue_same_issue")' in engine
    assert 'result.put("mode", "discovery")' in engine


def test_android_app_requires_armed_backup_and_persists_reconciliation_candidate():
    activity = (ROOT / "mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java").read_text(encoding="utf-8")
    assert 'getBoolean("backup_body_armed", false)' in activity
    assert 'EmergencyPulseEngine.runOnePulse' in activity
    assert 'writePrivateJson(RECONCILE_FILE, result)' in activity
    assert 'Run One Local Emergency Pulse' in activity
    assert 'candidate-only' in activity


def test_phone_body_does_not_replace_primary_pulse_network():
    doc = (ROOT / "docs/GENESIS_ANDROID_EMERGENCY_PULSES.md").read_text(encoding="utf-8")
    assert "Primary continuity: Gene Pulse Network" in doc
    assert "not a new Gene" in doc
    assert "cannot directly modify canonical Genesis source" in doc
    assert "performs exactly one bounded planning/analysis step" in doc

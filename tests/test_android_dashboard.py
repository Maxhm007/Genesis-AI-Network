from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_app_exposes_native_genesis_dashboard():
    main = (ROOT / "mobile" / "app" / "src" / "main" / "java" / "org" / "genesisai" / "mobile" / "MainActivity.java").read_text(encoding="utf-8")
    dashboard = (ROOT / "mobile" / "app" / "src" / "main" / "java" / "org" / "genesisai" / "mobile" / "GenesisDashboard.java").read_text(encoding="utf-8")

    assert 'dashboardButton.setText("Open Genesis Dashboard")' in main
    assert 'showGenesisDashboard()' in main
    assert 'GenesisDashboard.render(snapshot, localPulse, armed, live)' in main
    assert '"/v1/owner/dashboard"' in main
    assert 'readPrivateJson(SNAPSHOT_FILE)' in main

    assert '"GENESIS DASHBOARD\\n"' in dashboard
    assert '"Identity: Genesis = 1\\n"' in dashboard
    assert '"Open issues/tasks: "' in dashboard
    assert '"Backup body: "' in dashboard
    assert '"Primary continuity: Gene Pulse Network\\n"' in dashboard
    assert '"Phone authority: candidate-only"' in dashboard

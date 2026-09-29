from pathlib import Path

from genesis.communication_server import GenesisCommunicationHandler


def test_team_chat_ui_contains_nexus_team_layout():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert "Genesis Team Chat" in html
    assert "Nexus — Team Leader" in html
    assert "Message Nexus" in html
    assert "/v1/team" in html
    for name in ("Atlas", "Forge", "Sentinel", "Scout", "Recovery"):
        assert name in html


def test_team_status_uses_genesis_teammate_config():
    source = Path("genesis/communication_server.py").read_text(encoding="utf-8")
    assert 'config/genesis_teammates.json' in source
    assert '"/v1/team"' in source
    assert "autonomous_development" in source
    assert "nexus_can_evolve_team" in source

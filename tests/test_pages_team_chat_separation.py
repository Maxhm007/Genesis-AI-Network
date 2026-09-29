from pathlib import Path


def test_pages_deploys_command_center_at_root_and_team_chat_separately():
    text = Path(".github/workflows/deploy-team-chat-pages.yml").read_text(encoding="utf-8")
    assert "cp -a docs/status/. _site/" in text
    assert "mkdir -p _site/team-chat" in text
    assert "cp web/index.html _site/team-chat/index.html" in text
    assert "path: _site" in text


def test_team_chat_remains_its_own_page():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert "<title>Genesis Team Chat</title>" in html
    assert "Nexus — Team Leader" in html

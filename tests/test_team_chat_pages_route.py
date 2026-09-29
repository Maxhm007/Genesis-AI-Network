from pathlib import Path


def test_team_chat_exists_for_all_supported_pages_sources():
    for path in (
        Path("team-chat/index.html"),
        Path("docs/team-chat/index.html"),
        Path("docs/status/team-chat/index.html"),
    ):
        assert path.exists(), path
        text = path.read_text(encoding="utf-8")
        assert "<title>Genesis Team Chat</title>" in text
        assert "Nexus — Team Leader" in text

from pathlib import Path

from scripts.genesis_teammate import casual_response


def test_neutral_conversation_does_not_spawn_work():
    assert casual_response("Hi")
    assert casual_response("Thank you")
    assert casual_response("OK")
    assert casual_response("Check issue 867") is None


def test_team_prompt_requires_neutral_language():
    text = Path("scripts/genesis_teammate.py").read_text(encoding="utf-8")
    assert "Use neutral, professional, non-personified language." in text


def test_team_chat_matches_approved_information_architecture():
    html = Path("web/index.html").read_text(encoding="utf-8")
    for marker in (
        "Genesis Team Chat",
        "Nexus — Team Leader",
        "Teammates",
        "Open Tasks",
        "Recent Team Activity",
        "Genesis AI Network",
        "Architecture",
        "Development",
        "Validation",
        "Recovery",
    ):
        assert marker in html
    assert "conversationsInner" in html
    assert "mobileTeam" in html


def test_pages_routes_share_redesigned_team_chat():
    expected = Path("web/index.html").read_text(encoding="utf-8")
    for path in (
        Path("team-chat/index.html"),
        Path("docs/team-chat/index.html"),
        Path("docs/status/team-chat/index.html"),
    ):
        assert path.read_text(encoding="utf-8") == expected

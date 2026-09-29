from pathlib import Path

PAGES = (
    Path("web/index.html"),
    Path("team-chat/index.html"),
    Path("docs/team-chat/index.html"),
    Path("docs/status/team-chat/index.html"),
)

def test_visual_reference_structure_is_present():
    text = Path("web/index.html").read_text(encoding="utf-8")
    for marker in (
        "Genesis Team Chat",
        "Nexus — Team Leader",
        "Teammates",
        "Open Tasks",
        "Recent Team Activity",
        "AI teammates. Real progress.",
        "Product Launch",
        "Bug Triage",
        "Website Review",
        "Research",
    ):
        assert marker in text

def test_pages_routes_are_in_sync():
    expected = PAGES[0].read_text(encoding="utf-8")
    for path in PAGES[1:]:
        assert path.read_text(encoding="utf-8") == expected

def test_live_nexus_chat_is_preserved():
    text = Path("web/index.html").read_text(encoding="utf-8")
    assert "NEXUS_ISSUE=1000" in text
    assert "postComment" in text
    assert "waitResult" in text
    assert "Connect GitHub" in text

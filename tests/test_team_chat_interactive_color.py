from pathlib import Path

PAGES = (
    Path("web/index.html"),
    Path("team-chat/index.html"),
    Path("docs/team-chat/index.html"),
    Path("docs/status/team-chat/index.html"),
)

def test_desktop_controls_are_interactive():
    text = Path("web/index.html").read_text(encoding="utf-8")
    for marker in (
        'data-view="home"',
        'data-view="chats"',
        'data-view="teammates"',
        'data-view="tasks"',
        'data-view="settings"',
        "showTeamView",
        "showTaskView",
        "showSettings",
        "bindAgentClicks",
        "workspaceMenu",
    ):
        assert marker in text

def test_agent_color_tones_are_present():
    text = Path("web/index.html").read_text(encoding="utf-8")
    for tone in ("tone-nexus","tone-atlas","tone-forge","tone-sentinel","tone-scout","tone-recovery"):
        assert tone in text

def test_live_nexus_connection_is_preserved():
    text = Path("web/index.html").read_text(encoding="utf-8")
    assert "NEXUS_ISSUE=1000" in text
    assert "postComment" in text
    assert "waitResult" in text

def test_pages_routes_are_identical():
    expected = PAGES[0].read_text(encoding="utf-8")
    for path in PAGES[1:]:
        assert path.read_text(encoding="utf-8") == expected

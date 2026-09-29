from pathlib import Path

PAGES = (
    Path("web/index.html"),
    Path("team-chat/index.html"),
    Path("docs/team-chat/index.html"),
    Path("docs/status/team-chat/index.html"),
)

def test_live_pages_chat_targets_nexus_issue():
    for path in PAGES:
        text = path.read_text(encoding="utf-8")
        assert "NEXUS_ISSUE=1000" in text
        assert "postNexusComment" in text
        assert "waitForNexus" in text
        assert "genesis-nexus-result:" in text
        assert "Connect GitHub" in text
        assert "This is the public GitHub Pages preview" not in text

def test_token_is_not_embedded():
    for path in PAGES:
        text = path.read_text(encoding="utf-8")
        assert "github_pat_" not in text
        assert "ghp_" not in text

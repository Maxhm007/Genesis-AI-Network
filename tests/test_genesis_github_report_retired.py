from pathlib import Path


def test_hourly_report_script_cannot_create_reopen_or_comment_on_github_issues() -> None:
    text = Path("scripts/genesis_github_report.py").read_text(encoding="utf-8")

    assert "api.github.com" not in text
    assert "ensure_report_issue" not in text
    assert '"/issues' not in text
    assert "github_issue_channel\": \"retired" in text
    assert "genesis_hourly_report.txt" in text

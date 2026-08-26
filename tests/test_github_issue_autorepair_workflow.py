from pathlib import Path


WORKFLOW = Path(".github/workflows/github-issue-autorepair.yml")


def test_scheduled_autorepair_uses_bounded_fair_backlog_selection() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "--label genesis-autonomous --limit 100" in text
    assert "--json number,updatedAt,labels" in text
    assert "sort_by(.updatedAt, .number)" in text
    assert 'index("genesis-repair-in-progress")' in text


def test_autorepair_claim_is_always_released() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ensure_label genesis-repair-in-progress" in text
    assert "--add-label genesis-repair-in-progress" in text
    assert "if: always() && steps.issue.outputs.issue_number != ''" in text
    assert "--remove-label genesis-repair-in-progress" in text

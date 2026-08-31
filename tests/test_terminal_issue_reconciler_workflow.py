from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "github-issue-terminal-reconciler.yml"


def test_terminal_issue_reconciler_workflow_is_continuous_and_safe():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Genesis Terminal Issue Reconciler" in text
    assert "cron: '*/5 * * * *'" in text
    assert "workflow_dispatch:" in text
    assert "issues: write" in text
    assert "contents: read" in text
    assert "cancel-in-progress: false" in text
    assert "reconcile_terminal_github_issues" in text
    assert "from genesis.github_issue_terminal_reconciler import" in text
    assert "git push" not in text
    assert "gh issue close" not in text


def test_terminal_issue_reconciler_uses_existing_authority_not_custom_closure_rules():
    text = WORKFLOW.read_text(encoding="utf-8")

    # The workflow must delegate closure decisions to the existing reconciler.
    # It must not implement its own title/label based bulk-close policy.
    assert "reconcile_terminal_github_issues(Path('.'))" in text
    assert "state=closed" not in text
    assert "state_reason" not in text


def test_terminal_issue_reconciler_restores_and_resaves_resumable_task_cache():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/cache/restore@v4" in text
    assert "actions/cache/save@v4" in text
    assert "path: runtime" in text
    assert "genesis-terminal-runtime-" in text
    assert "gene-runtime-gene-node-1-" in text
    assert text.index("actions/cache/restore@v4") < text.index("reconcile_terminal_github_issues")
    assert text.index("reconcile_terminal_github_issues") < text.index("actions/cache/save@v4")

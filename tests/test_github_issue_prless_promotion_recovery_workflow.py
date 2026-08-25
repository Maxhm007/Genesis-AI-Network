from pathlib import Path


WORKFLOW = Path(".github/workflows/github-issue-prless-promotion-recovery.yml").read_text(encoding="utf-8")


def test_recovery_is_only_a_failed_autorepair_or_manual_fallback():
    assert 'workflows: ["Genesis GitHub Issue Autorepair"]' in WORKFLOW
    assert "github.event.workflow_run.conclusion == 'failure'" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "genesis-autonomous" in WORKFLOW


def test_recovery_reuses_exact_candidate_and_full_safety_gates():
    assert "Genesis created candidate" in WORKFLOW
    assert "candidate evidence SHA does not match branch head" in WORKFLOW
    assert "Independent full test suite A" in WORKFLOW
    assert "Independent full test suite B" in WORKFLOW
    assert "Security review A" in WORKFLOW
    assert "Security review B" in WORKFLOW
    assert "scripts/secret_guard.py --history" in WORKFLOW
    assert "scripts/verify_validator_votes.py" in WORKFLOW
    assert "GENESIS_CONSTITUTION.md|GENESIS_BLOCK.json|\\.github/" in WORKFLOW


def test_pr_is_observability_not_a_promotion_dependency():
    assert "gh pr create" not in WORKFLOW
    assert "pull-requests: write" not in WORKFLOW
    assert 'git push origin "$CANDIDATE_SHA:refs/heads/main"' in WORKFLOW
    assert "--force" not in WORKFLOW
    assert "Promote exact validated candidate without requiring a PR" in WORKFLOW

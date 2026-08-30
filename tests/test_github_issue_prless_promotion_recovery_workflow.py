from pathlib import Path


WORKFLOW = Path(".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")


def test_promotion_reuses_exact_candidate_without_pr_dependency() -> None:
    assert 'CANDIDATE_SHA: ${{ steps.evidence.outputs.candidate_sha }}' in WORKFLOW
    assert 'git cat-file -e "${CANDIDATE_SHA}^{commit}"' in WORKFLOW
    assert 'git cherry-pick "$CANDIDATE_SHA"' in WORKFLOW
    assert "gh pr create" not in WORKFLOW
    assert "pull-requests: write" not in WORKFLOW


def test_promotion_revalidates_on_latest_main_before_push() -> None:
    assert "for integration_attempt in 1 2 3" in WORKFLOW
    assert 'git checkout -B "genesis/integration-${ISSUE_NUMBER}-${GITHUB_RUN_ID}" origin/main' in WORKFLOW
    assert 'latest_main=$(git rev-parse origin/main)' in WORKFLOW
    assert "main moved during validation; rebuilding on latest main" in WORKFLOW
    assert "python -m py_compile \"$TARGET\"" in WORKFLOW
    assert "python -m pytest -q" in WORKFLOW


def test_prless_promotion_is_non_force_and_evidence_gated() -> None:
    assert "git push origin HEAD:main" in WORKFLOW
    assert "--force" not in WORKFLOW
    assert "genesis-verified" in WORKFLOW
    assert "state=closed" in WORKFLOW

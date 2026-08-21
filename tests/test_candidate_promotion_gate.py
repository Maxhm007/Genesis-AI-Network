from pathlib import Path


def test_candidate_promotion_requires_exact_head_validated_provenance() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "candidate-promotion.yml").read_text(encoding="utf-8")

    assert "pull-requests: read" in workflow
    assert "checks: read" in workflow
    assert "gh pr list" in workflow
    assert "headRefOid" in workflow
    assert "source_sha=$(git rev-parse" in workflow
    assert "commits/${source_sha}/check-runs?per_page=100" in workflow

    for check_name in (
        "validator_a",
        "validator_b",
        "secret_guard",
        "Validator A",
        "Validator B",
        "Independent quorum gate",
    ):
        assert check_name in workflow

    assert "required exact-head check is not successful" in workflow
    assert "no open non-draft PR for exact head" in workflow


def test_candidate_promotion_revalidates_rebased_candidate_before_main() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "candidate-promotion.yml").read_text(encoding="utf-8")

    assert workflow.count("review_candidate('origin/main')") >= 3
    assert "Security review staged candidate A" in workflow
    assert "Security review staged candidate B" in workflow
    assert "Re-verify exact staged candidate boundary and security" in workflow
    assert workflow.count("grep -Eq '^\\.github/'") >= 3
    assert workflow.count("GENESIS_CONSTITUTION.md|GENESIS_BLOCK.json") >= 3
    assert "Verify signed two-job quorum" in workflow
    assert 'test "$(git rev-parse origin/${{ needs.prepare.outputs.candidate_branch }})" = "$candidate"' in workflow
    assert 'git merge-base --is-ancestor "$main_sha" "$candidate"' in workflow
    assert 'git push origin "$candidate:refs/heads/main"' in workflow

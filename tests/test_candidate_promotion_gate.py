from pathlib import Path


def test_internal_review_publishes_exact_approval_ref_and_requests_promotion() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")

    publish = workflow[workflow.index("Publish internally reviewed exact candidate") : workflow.index("Remove rejected isolated review ref")]
    assert "if: steps.pulse.outputs.has_validation_candidate == 'true'" in publish
    assert 'approval_ref="genesis/approved-${candidate}"' in publish
    assert 'git push --force origin "$candidate:refs/heads/$approval_ref"' in publish
    assert 'gh workflow run candidate-promotion.yml --repo "$GITHUB_REPOSITORY" --ref main' in publish
    assert workflow.count('approval_ref="genesis/approved-${candidate}"') == 1


def test_candidate_promotion_requires_exact_internal_review_approval_ref() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "candidate-promotion.yml").read_text(encoding="utf-8")

    assert "+refs/heads/genesis/candidate-*" in workflow
    assert "+refs/heads/genesis/approved-*" in workflow
    assert 'approval_branch="genesis/approved-${source_sha}"' in workflow
    assert 'approval_ref="refs/remotes/origin/${approval_branch}"' in workflow
    assert 'git show-ref --verify --quiet "$approval_ref"' in workflow
    assert 'approval_sha=$(git rev-parse "$approval_ref")' in workflow
    assert '[[ "$approval_sha" != "$source_sha" ]]' in workflow
    assert "exact internal-review approval ref is missing" in workflow
    assert "approval ref does not match exact candidate SHA" in workflow
    assert "approval_branch=$selected_approval" in workflow


def test_candidate_promotion_revalidates_rebased_candidate_before_main() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "candidate-promotion.yml").read_text(encoding="utf-8")

    assert workflow.count("review_candidate('origin/main')") >= 3
    assert "Security review staged candidate A" in workflow
    assert "Security review staged candidate B" in workflow
    assert "Re-verify exact staged candidate boundary and security" in workflow
    assert workflow.count("grep -Eq '^\\.github/'") >= 3
    assert workflow.count("GENESIS_CONSTITUTION.md|GENESIS_BLOCK.json") >= 3
    assert "Independent full test suite A" in workflow
    assert "Independent full test suite B" in workflow
    assert "Verify signed two-job quorum" in workflow
    assert 'test "$(git rev-parse origin/${{ needs.prepare.outputs.candidate_branch }})" = "$candidate"' in workflow
    assert 'git merge-base --is-ancestor "$main_sha" "$candidate"' in workflow
    assert 'git push origin "$candidate:refs/heads/main"' in workflow
    assert 'git push origin --delete "$approval" || true' in workflow

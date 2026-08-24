from pathlib import Path


def test_chained_pulses_require_exact_parent_runtime_cache() -> None:
    root = Path(__file__).resolve().parents[1]
    gene = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")
    coding = (root / ".github" / "workflows" / "coding-intelligence-pulse.yml").read_text(encoding="utf-8")

    exact_key = "key: gene-runtime-${{ env.GENE_ID }}-${{ env.RUNTIME_PARENT_RUN_ID }}"
    parent_arg = '-f runtime_parent_run_id="$GITHUB_RUN_ID"'

    for workflow in (gene, coding):
        assert "runtime_parent_run_id:" in workflow
        assert "RUNTIME_PARENT_RUN_ID:" in workflow
        assert "Restore exact predecessor Gene state" in workflow
        assert "if: env.RUNTIME_PARENT_RUN_ID != ''" in workflow
        assert exact_key in workflow
        assert "fail-on-cache-miss: true" in workflow
        assert "if: env.RUNTIME_PARENT_RUN_ID == ''" in workflow
        assert "restore-keys: |" in workflow

    assert parent_arg in gene
    assert parent_arg in coding


def test_broad_runtime_restore_is_standalone_only() -> None:
    root = Path(__file__).resolve().parents[1]
    workflows = [
        (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8"),
        (root / ".github" / "workflows" / "coding-intelligence-pulse.yml").read_text(encoding="utf-8"),
    ]

    for workflow in workflows:
        standalone_guard = "if: env.RUNTIME_PARENT_RUN_ID == ''"
        broad_restore = "gene-runtime-${{ env.GENE_ID }}-"
        assert standalone_guard in workflow
        assert broad_restore in workflow
        assert workflow.index(standalone_guard) < workflow.index("restore-keys: |")

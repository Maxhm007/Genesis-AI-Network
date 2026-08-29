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


def test_broad_runtime_restore_is_standalone_or_explicit_recovery_only() -> None:
    root = Path(__file__).resolve().parents[1]
    gene = (root / ".github" / "workflows" / "gene-pulse.yml").read_text(encoding="utf-8")
    coding = (root / ".github" / "workflows" / "coding-intelligence-pulse.yml").read_text(encoding="utf-8")

    standalone_guard = "if: env.RUNTIME_PARENT_RUN_ID == ''"
    recovery_guard = "if: env.RUNTIME_PARENT_RUN_ID != '' && steps.exact_runtime.outcome != 'success'"
    broad_restore = "gene-runtime-${{ env.GENE_ID }}-"

    assert recovery_guard in gene
    assert gene.index(recovery_guard) < gene.index("restore-keys: |")
    assert standalone_guard in gene
    assert broad_restore in gene

    assert standalone_guard in coding
    assert broad_restore in coding
    assert coding.index(standalone_guard) < coding.index("restore-keys: |")

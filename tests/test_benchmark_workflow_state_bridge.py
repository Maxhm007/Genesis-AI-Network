from pathlib import Path


def test_benchmark_workflows_and_proactive_share_gene_runtime_namespace() -> None:
    benchmark = Path('.github/workflows/benchmark-evaluation.yml').read_text(encoding='utf-8')
    baseline = Path('.github/workflows/swe-bench-pro-bootstrap-baseline.yml').read_text(encoding='utf-8')
    proactive = Path('.github/workflows/proactive-development.yml').read_text(encoding='utf-8')

    assert 'path: runtime' in benchmark
    assert 'key: gene-runtime-gene-node-1-${{ github.run_id }}-benchmark-evaluation' in benchmark
    assert 'gene-runtime-gene-node-1-' in benchmark

    assert 'path: runtime' in baseline
    assert 'gene-runtime-${{ env.GENE_ID }}-' in baseline

    assert 'path: runtime' in proactive
    assert 'key: gene-runtime-gene-node-1-${{ github.run_id }}-proactive' in proactive
    assert 'gene-runtime-gene-node-1-' in proactive

    assert 'genesis-runtime-${{ runner.os }}-' not in benchmark
    assert 'genesis-runtime-${{ runner.os }}-' not in proactive

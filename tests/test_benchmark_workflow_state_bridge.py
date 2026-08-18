from pathlib import Path


def test_benchmark_workflow_returns_state_to_proactive_runtime_namespace() -> None:
    workflow = Path('.github/workflows/benchmark-evaluation.yml').read_text(encoding='utf-8')
    assert 'key: genesis-runtime-${{ runner.os }}-benchmark-${{ github.run_id }}' in workflow
    assert 'genesis-runtime-${{ runner.os }}-${{ github.event.workflow_run.id }}' in workflow
    assert 'genesis-runtime-${{ runner.os }}-' in workflow
    assert 'key: genesis-benchmark-' not in workflow

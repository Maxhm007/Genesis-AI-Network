"""Regression checks for safely reactivated Agentic Lab workers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_agentic_strategy_and_deepseek_are_test_first():
    for filename, job in (
        ("genesis-agentic-strategy-worker.yml", "  repair-and-promote:"),
        ("genesis-deepseek-agentic-solver.yml", "  solve:"),
    ):
        source = (ROOT / filename).read_text(encoding="utf-8")
        gate, worker = source.split(job, 1)
        assert "  test-first-gate:" in gate
        assert "Verify repair control plane before model installation" in gate
        assert "tests/test_repair_checkpoints.py" in gate
        assert "gh issue view" in gate
        assert "needs: test-first-gate" in worker
        assert "needs.test-first-gate.result == 'success'" in worker
        assert "if: false" not in worker
        assert "python -m pytest -q" in worker


def test_agentic_lab_has_hourly_wake_and_tests_before_dispatch():
    source = (ROOT / "genesis-agentic-lab-recovery.yml").read_text(encoding="utf-8")
    assert "  schedule:\n    - cron: '17 * * * *'" in source
    assert "  dispatch-agentic-pool:" in source
    part = source.split("  dispatch-agentic-pool:", 1)[1]
    assert part.index("Validate parallel controller and cross-Gene delegation") < part.index("Dispatch bounded parallel Agentic lanes")
    assert "run: python -m pytest -q tests/test_agentic_parallel_dispatch.py tests/test_gene_backlog_delegation_router.py" in part
    assert "if: github.event_name == 'push'\n        run: python -m pytest" not in part

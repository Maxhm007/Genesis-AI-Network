from pathlib import Path


def test_agentic_lab_is_single_queue_authority_and_workers_are_per_issue_serialized():
    agentic = Path(".github/workflows/genesis-agentic-lab-recovery.yml").read_text()
    worker = Path(".github/workflows/genesis-bounded-repair-worker.yml").read_text()
    sequential = Path(".github/workflows/genesis-sequential-issue-controller.yml").read_text()

    assert "group: genesis-bounded-repair-" in worker
    assert "cancel-in-progress: false" in worker
    assert "agentic_parallel_dispatch.py" in agentic
    assert "Agentic Lab is the single issue-routing and strategy authority" in sequential
    assert "genesis-bounded-repair-worker.yml" not in sequential
    assert not Path(".github/workflows/genesis-oldest-issue-solver.yml").exists()
    assert not Path(".github/workflows/genesis-priority-issue-solver.yml").exists()

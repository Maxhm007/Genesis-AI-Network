from pathlib import Path

from scripts.requeue_exhausted_issues import ENGINE_PATHS


ROOT = Path(__file__).resolve().parents[1]
SPECIALIST_CONTROLLER = ROOT / ".github/workflows/genesis-specialist-issue-controller.yml"
SPECIALIST_WORKER = ROOT / ".github/workflows/genesis-specialist-repair-worker-v2.yml"
GENERIC_CONTROLLER = ROOT / ".github/workflows/genesis-sequential-issue-controller.yml"
GENERIC_WORKER = ROOT / ".github/workflows/genesis-bounded-repair-worker.yml"


def test_evidence_first_builder_changes_repair_engine_generation() -> None:
    assert "genesis/github_issue_capability_builder.py" in ENGINE_PATHS


def test_specialist_controller_is_feeder_only_and_agentic_lab_owns_routing() -> None:
    specialist = SPECIALIST_CONTROLLER.read_text(encoding="utf-8")
    agentic = (ROOT / "scripts/agentic_lab_recovery_dispatch.py").read_text(encoding="utf-8")

    assert "Agentic Lab owns specialist classification, reservation, and worker dispatch" in specialist
    assert "gh workflow run genesis-agentic-lab-recovery.yml" in specialist
    assert "issues: write" not in specialist
    assert 'target.startswith("scripts/")' in agentic
    assert 'target.endswith(".py")' in agentic
    assert "PROTECTED_TARGETS" in agentic


def test_specialist_worker_uses_grounded_guarded_repair_engine_and_exact_scope() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert '"$target" != scripts/*.py' in worker
    assert "scripts/secret_guard.py" in worker
    assert "scripts/privileged_change_gate.py" in worker
    assert "python scripts/specialist_issue_autorepair.py" in worker
    assert '[[ "$path" == "$TARGET" || "$path" == "$target_test" ]]' in worker
    assert 'python -m py_compile "$TARGET"' in worker
    assert 'python -m pytest -q "$target_test"' in worker
    assert "python -m pytest -q" in worker
    assert "git push origin HEAD:main" in worker
    assert "Genesis grounded specialist repair attempt" in worker
    assert "genesis-issue-closure-manager.yml" in worker
    assert "state=closed -f state_reason=completed" not in worker
    assert "The Issue remains open and unresolved; it was not falsely closed." in worker


def test_generic_worker_remains_package_code_only() -> None:
    worker = GENERIC_WORKER.read_text(encoding="utf-8")
    assert '"$target" != genesis/*.py' in worker

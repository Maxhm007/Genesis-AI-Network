from pathlib import Path

from scripts.requeue_exhausted_issues import ENGINE_PATHS


ROOT = Path(__file__).resolve().parents[1]
SPECIALIST_CONTROLLER = ROOT / ".github/workflows/genesis-specialist-issue-controller.yml"
SPECIALIST_WORKER = ROOT / ".github/workflows/genesis-specialist-repair-worker.yml"
GENERIC_CONTROLLER = ROOT / ".github/workflows/genesis-sequential-issue-controller.yml"
GENERIC_WORKER = ROOT / ".github/workflows/genesis-bounded-repair-worker.yml"


def test_evidence_first_builder_changes_repair_engine_generation() -> None:
    assert "genesis/github_issue_capability_builder.py" in ENGINE_PATHS


def test_specialist_controller_serializes_with_generic_queue_and_routes_only_safe_scripts() -> None:
    specialist = SPECIALIST_CONTROLLER.read_text(encoding="utf-8")
    generic = GENERIC_CONTROLLER.read_text(encoding="utf-8")

    assert "group: genesis-sequential-issue-controller" in specialist
    assert "group: genesis-sequential-issue-controller" in generic
    assert "target.startswith('scripts/')" in specialist
    assert "target.endswith('.py')" in specialist
    assert "scripts/secret_guard.py" in specialist
    assert "scripts/privileged_change_gate.py" in specialist
    assert "scripts/verify_validator_votes.py" in specialist
    assert "scripts/action_repair_guard.py" in specialist
    assert "scripts/issue_acceptance_guard.py" in specialist
    assert "genesis-repair-in-progress" in specialist
    assert "genesis-specialist-repair-worker.yml" in specialist


def test_specialist_worker_uses_existing_guarded_repair_engine_and_exact_scope() -> None:
    worker = SPECIALIST_WORKER.read_text(encoding="utf-8")

    assert '"$target" != scripts/*.py' in worker
    assert "scripts/secret_guard.py" in worker
    assert "scripts/privileged_change_gate.py" in worker
    assert "python scripts/github_issue_autorepair.py" in worker
    assert 'if [[ "$path" != "$TARGET" && "$path" != "$target_test" ]]' in worker
    assert 'python -m py_compile "$TARGET"' in worker
    assert 'python -m pytest -q "$target_test"' in worker
    assert "python -m pytest -q" in worker
    assert "git push origin HEAD:main" in worker
    assert "genesis-specialist-repair-attempt:" in worker
    assert "state=closed -f state_reason=not_planned" in worker


def test_generic_worker_remains_package_code_only() -> None:
    worker = GENERIC_WORKER.read_text(encoding="utf-8")
    assert '"$target" != genesis/*.py' in worker

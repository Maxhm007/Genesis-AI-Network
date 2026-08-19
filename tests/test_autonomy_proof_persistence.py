from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger


def test_autonomy_proof_lives_in_cached_task_reviews(tmp_path: Path) -> None:
    ledger = AutonomyProofLedger(tmp_path)
    assert ledger.path == tmp_path / "runtime" / "task_reviews" / "autonomy_proof.jsonl"
    ledger.record(cycle_id="c1", stage="cycle_complete", actor="genesis.coding", outcome="success")
    restored = AutonomyProofLedger(tmp_path)
    assert restored.report()["genesis_autonomous_cycles"] == 1
    assert restored.report()["proof_path"] == "runtime/task_reviews/autonomy_proof.jsonl"


def test_legacy_autonomy_proof_is_migrated(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    legacy = runtime / "autonomy_proof.jsonl"
    legacy.write_text(
        '{"cycle_id":"old","stage":"cycle_complete","actor":"genesis.coding","classification":"genesis_autonomous","outcome":"success","details":{},"recorded_at":"2026-08-19T00:00:00+00:00"}\n',
        encoding="utf-8",
    )
    ledger = AutonomyProofLedger(tmp_path)
    assert ledger.report()["genesis_autonomous_cycles"] == 1

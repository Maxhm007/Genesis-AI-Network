from pathlib import Path

from genesis.autonomy_proof import AutonomyProofLedger
from genesis.velocity import AdaptiveVelocityController


def _complete(ledger: AutonomyProofLedger, index: int, actor: str = "genesis.proactive", outcome: str = "success") -> None:
    ledger.record(cycle_id=f"c{index}", stage="cycle_complete", actor=actor, outcome=outcome)


def test_autonomy_proof_does_not_credit_external_work(tmp_path: Path):
    ledger = AutonomyProofLedger(tmp_path)
    _complete(ledger, 1, actor="external")
    report = ledger.report()
    assert report["genesis_autonomous_cycles"] == 0
    assert report["external_cycles"] == 1
    assert report["autonomous_ratio"] == 0.0


def test_autonomy_proof_reaches_proven_status_after_repeated_genesis_cycles(tmp_path: Path):
    ledger = AutonomyProofLedger(tmp_path)
    for i in range(5):
        _complete(ledger, i)
    report = ledger.report()
    assert report["proof_status"] == "proven"
    assert report["autonomous_ratio"] == 1.0


def test_velocity_accelerates_only_after_validated_autonomous_history(tmp_path: Path):
    ledger = AutonomyProofLedger(tmp_path)
    controller = AdaptiveVelocityController(tmp_path)
    assert controller.policy()["acceleration_level"] == 1
    for i in range(10):
        _complete(ledger, i)
    policy = controller.policy()
    assert policy["acceleration_level"] >= 4
    assert policy["max_development_burst"] >= 4
    assert policy["recommended_parallel_candidates"] >= 3
    assert policy["cycle_interval_multiplier"] <= 0.5


def test_velocity_slows_immediately_after_risk_event(tmp_path: Path):
    ledger = AutonomyProofLedger(tmp_path)
    for i in range(15):
        _complete(ledger, i)
    fast = AdaptiveVelocityController(tmp_path).policy()
    _complete(ledger, 99, outcome="security_rejected")
    slowed = AdaptiveVelocityController(tmp_path).policy()
    assert slowed["acceleration_level"] < fast["acceleration_level"]
    assert slowed["recent_risk_events"] == 1

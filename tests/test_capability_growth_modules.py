from pathlib import Path

import pytest

from genesis.evaluation import EvaluationModule
from genesis.experiment import ExperimentModule
from genesis.resource import ResourceModule
from genesis.model_scout import ModelScoutModule
from genesis.evidence import EvidenceModule
from genesis.peer_compute import PeerComputeModule
from genesis.modules.registry import ModuleRegistry


def test_evaluation_unmeasured_gets_zero_credit():
    result = EvaluationModule().evaluate("reasoning", None, 100, evidence_count=0)
    assert result.score == 0
    assert result.normalized == 0


def test_experiment_requires_measured_gain():
    module = ExperimentModule()
    assert module.compare("improve", 0.5, 0.7, 0.05).decision == "keep"
    assert module.compare("improve", 0.5, 0.51, 0.05).decision == "reject"


def test_resource_capacity_is_bounded_and_penalizes_low_battery():
    module = ResourceModule()
    normal = module.snapshot(20, 20, 20, battery_percent=80)
    low = module.snapshot(20, 20, 20, battery_percent=10)
    assert 0 <= module.capacity_score(normal) <= 100
    assert module.capacity_score(low) < module.capacity_score(normal)


def test_model_scout_uses_sequential_trust_lifecycle():
    module = ModelScoutModule()
    candidate = module.candidate("model", "https://example.invalid/model", "Apache-2.0")
    candidate = module.transition(candidate, "quarantined")
    candidate = module.transition(candidate, "tested", benchmark_score=0.7, resource_cost=1.0)
    candidate = module.transition(candidate, "validated")
    assert candidate.state == "validated"
    with pytest.raises(ValueError):
        module.transition(candidate, "active")


def test_evidence_requires_review_before_validation():
    module = EvidenceModule()
    record = module.record("claim", "paper", "doi:test", 0.6)
    with pytest.raises(ValueError):
        module.transition(record, "validated")
    reviewed = module.transition(record, "reviewed")
    validated = module.transition(reviewed, "validated", 0.9)
    assert validated.status == "validated"


def test_peer_compute_verifies_content_hash():
    module = PeerComputeModule()
    lease = module.lease("task-1", "peer-a", "simulation", {"x": 1})
    output = {"answer": 2}
    digest = module.hash_payload(output)
    assert module.verify_result(lease, output, digest).verified is True
    assert module.verify_result(lease, output, "0" * 64).verified is False


def test_growth_modules_register_from_extension_manifest(tmp_path: Path):
    source = Path("config/modules.d/capability_growth.json")
    target = tmp_path / "config" / "modules.d"
    target.mkdir(parents=True)
    (target / "capability_growth.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    registry = ModuleRegistry.from_default_config(tmp_path)
    expected = {
        "genesis.evaluation", "genesis.experiment", "genesis.resource",
        "genesis.model_scout", "genesis.evidence", "genesis.peer_compute",
    }
    assert expected.issubset({module.module_id for module in registry.active()})

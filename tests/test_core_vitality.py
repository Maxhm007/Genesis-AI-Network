from pathlib import Path
import json

from genesis.core_vitality import CoreVitalityMonitor

ROOT = Path(__file__).resolve().parents[1]


def test_core_vitality_requires_all_three_loops():
    report = CoreVitalityMonitor(ROOT).evaluate()
    assert report["required_loops"] == ["self_development", "reproduction", "mission"]
    assert set(report["loops"]) == {"self_development", "reproduction", "mission"}
    assert report["operational"] is True
    assert report["failed_loops"] == []


def test_reproduction_means_bounded_readiness_not_uncontrolled_spawning():
    policy = json.loads((ROOT / "config" / "core_vitality.json").read_text(encoding="utf-8"))
    assert policy["reproduction"]["mode"] == "authorized_readiness"
    assert policy["reproduction"]["uncontrolled_spawning"] is False
    report = CoreVitalityMonitor(ROOT).evaluate()
    assert report["loops"]["reproduction"]["active"] is True


def test_core_failure_is_highest_priority(tmp_path):
    for name in [
        "GENESIS_CONSTITUTION.md",
        "GENESIS_BLOCK.json",
        "CURRENT_TASK.md",
        "SELF_DEVELOPMENT_POLICY.md",
        "GENE_IDENTITY.json",
    ]:
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    (tmp_path / "genesis").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "config" / "replication.json").write_bytes((ROOT / "config" / "replication.json").read_bytes())
    report = CoreVitalityMonitor(tmp_path).evaluate()
    assert report["operational"] is False
    assert report["repair_priority"] == "highest"
    assert "self_development" in report["failed_loops"]
    repair = json.loads((tmp_path / "runtime" / "core_vitality_repair.json").read_text(encoding="utf-8"))
    assert repair["priority"] == "highest"

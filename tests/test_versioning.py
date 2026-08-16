from pathlib import Path

from genesis.modules.types import ModuleManifest
from genesis.modules.versioning import ModuleVersionManager


def manifest(version: str) -> ModuleManifest:
    return ModuleManifest(
        module_id="genesis.research",
        name="Research Module",
        version=version,
        purpose="Research",
        capabilities=["scientific_research"],
        permissions=["network.read"],
    )


def test_version_history_and_rollback_target(tmp_path: Path):
    manager = ModuleVersionManager(tmp_path / "versions.json")
    manager.record_validated(manifest("1.0.0"), {"percent": 70})
    manager.record_validated(manifest("1.1.0"), {"percent": 82})
    history = manager.history("genesis.research")
    assert [item.version for item in history] == ["1.0.0", "1.1.0"]
    target = manager.rollback_target("genesis.research", "1.1.0")
    assert target is not None
    assert target.version == "1.0.0"


def test_regression_triggers_rollback_decision():
    assert ModuleVersionManager.should_rollback(82, 70) is True
    assert ModuleVersionManager.should_rollback(70, 82) is False

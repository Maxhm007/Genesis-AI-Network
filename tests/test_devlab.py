from __future__ import annotations

from pathlib import Path

from genesis.devlab.module import GenesisDevLab
from genesis.devlab.workspace import EditProposal, LabWorkspace
from genesis.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_devlab_is_registered_without_direct_authority() -> None:
    registry = ModuleRegistry.from_default_config(ROOT)
    module = registry.get("genesis.devlab")
    assert module is not None
    assert module.status == "active"
    assert module.implementation == "genesis.devlab"
    assert module.metadata["direct_main_write"] is False
    assert module.metadata["validation_authority"] is False
    assert module.metadata["protected_file_bypass"] is False
    assert "genesis.validation" in module.dependencies


def test_lab_edit_never_mutates_original(tmp_path: Path) -> None:
    source = tmp_path / "genesis" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")

    workspace = LabWorkspace(tmp_path)
    snapshot = workspace.snapshot("genesis/sample.py")
    candidate = workspace.stage_edit(snapshot, EditProposal("genesis/sample.py", "VALUE = 2\n", "test"))

    assert source.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (tmp_path / candidate).read_text(encoding="utf-8") == "VALUE = 2\n"
    assert (tmp_path / snapshot.snapshot_path).read_text(encoding="utf-8") == "VALUE = 1\n"


def test_editor_rejects_cross_file_change(tmp_path: Path) -> None:
    source = tmp_path / "genesis" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    workspace = LabWorkspace(tmp_path)
    snapshot = workspace.snapshot("genesis/sample.py")

    try:
        workspace.stage_edit(snapshot, EditProposal("genesis/other.py", "VALUE = 2\n"))
    except ValueError as exc:
        assert "exactly the assigned file" in str(exc)
    else:
        raise AssertionError("cross-file DevLab edit should be rejected")


def test_inspector_reports_python_structure(tmp_path: Path) -> None:
    source = tmp_path / "genesis" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("import json\n\nclass A:\n    pass\n\ndef f():\n    return 1\n", encoding="utf-8")
    report = GenesisDevLab(tmp_path).inspect("genesis/sample.py")
    assert report.syntax_ok is True
    assert report.classes == ("A",)
    assert report.functions == ("f",)
    assert "json" in report.imports


def test_retry_planner_changes_method_and_stops() -> None:
    first = GenesisDevLab.retry_plan(0, max_attempts=3)
    second = GenesisDevLab.retry_plan(1, "first failed", max_attempts=3)
    third = GenesisDevLab.retry_plan(2, "second failed", max_attempts=3)
    exhausted = GenesisDevLab.retry_plan(3, "third failed", max_attempts=3)
    assert len({first.method, second.method, third.method}) == 3
    assert second.previous_error == "first failed"
    assert exhausted.exhausted is True

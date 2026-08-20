from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.devlab.code_oss import CodeOSSBridge
from genesis.modules.registry import ModuleRegistry


ROOT = Path(__file__).resolve().parents[1]


def _make_repo(root: Path) -> None:
    source = root / "genesis" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text(
        "from genesis.sample import VALUE\n\n\ndef test_value():\n    assert VALUE in {1, 2}\n",
        encoding="utf-8",
    )


def test_code_oss_session_is_isolated_from_canonical_source(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    bridge = CodeOSSBridge(tmp_path)
    session = bridge.create_session(("genesis/sample.py",))

    workspace = bridge.workspace_for(session)
    edited = workspace / "genesis" / "sample.py"
    edited.write_text("VALUE = 2\n", encoding="utf-8")
    proposal = bridge.candidate_proposal(session, "genesis/sample.py")

    assert proposal.target_path == "genesis/sample.py"
    assert proposal.content == "VALUE = 2\n"
    assert (tmp_path / "genesis" / "sample.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_code_oss_session_manifest_preserves_safeguards(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    bridge = CodeOSSBridge(tmp_path)
    session = bridge.create_session(("genesis/sample.py",))

    manifest = json.loads(
        (bridge.workspace_for(session) / ".genesis-code-oss-session.json").read_text(encoding="utf-8")
    )
    assert manifest["candidate_import_only"] is True
    assert manifest["direct_main_write"] is False
    assert manifest["validation_authority"] is False
    assert manifest["protected_file_bypass"] is False
    assert manifest["allowed_paths"] == ["genesis/sample.py"]


def test_code_oss_rejects_candidate_outside_authorized_paths(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    other = tmp_path / "genesis" / "other.py"
    other.write_text("OTHER = 1\n", encoding="utf-8")
    bridge = CodeOSSBridge(tmp_path)
    session = bridge.create_session(("genesis/sample.py",))

    with pytest.raises(PermissionError, match="not authorized"):
        bridge.candidate_proposal(session, "genesis/other.py")


def test_code_oss_rejects_unchanged_candidate(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    bridge = CodeOSSBridge(tmp_path)
    session = bridge.create_session(("genesis/sample.py",))

    with pytest.raises(ValueError, match="did not change"):
        bridge.candidate_proposal(session, "genesis/sample.py")


def test_code_oss_runs_tests_only_inside_isolated_workspace(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    bridge = CodeOSSBridge(tmp_path)
    session = bridge.create_session(("genesis/sample.py",))
    result = bridge.run_tests(session, ("tests/test_sample.py",), timeout_seconds=30)

    assert result.passed is True
    assert result.returncode == 0
    assert result.command[-1] == "tests/test_sample.py"


def test_devlab_registers_code_oss_without_new_authority() -> None:
    registry = ModuleRegistry.from_default_config(ROOT)
    module = registry.get("genesis.devlab")

    assert module is not None
    assert "code_oss_workspace" in module.capabilities
    assert "genesis.devlab.code_oss" in module.metadata["components"]
    assert module.metadata["code_oss"]["submodule_path"] == "vendor/code-oss"
    assert module.metadata["code_oss"]["candidate_import_only"] is True
    assert module.metadata["direct_main_write"] is False
    assert module.metadata["validation_authority"] is False

from pathlib import Path

import pytest

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


def _module(tmp_path: Path) -> CodingModule:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")
    return CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))


def test_accepts_top_level_single_edit_shape(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = module.validate_proposal(
        {
            "path": "genesis/example.py",
            "start_line": 1,
            "end_line": 1,
            "new": "VALUE = 3",
        },
        "test-coder",
    )
    assert proposal.files["genesis/example.py"] == "VALUE = 3\nOTHER = 2\n"


def test_accepts_single_edit_under_edit_key(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = module.validate_proposal(
        {
            "edit": {
                "path": "genesis/example.py",
                "start_line": 2,
                "end_line": 2,
                "new": "OTHER = 4",
            }
        },
        "test-coder",
    )
    assert proposal.files["genesis/example.py"] == "VALUE = 1\nOTHER = 4\n"


def test_accepts_single_edit_object_under_edits_key(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = module.validate_proposal(
        {
            "edits": {
                "path": "genesis/example.py",
                "old": "VALUE = 1",
                "new": "VALUE = 5",
            }
        },
        "test-coder",
    )
    assert proposal.files["genesis/example.py"] == "VALUE = 5\nOTHER = 2\n"


def test_does_not_invent_missing_edit_coordinates(tmp_path: Path) -> None:
    module = _module(tmp_path)
    with pytest.raises(ValueError, match="files mapping or compact edits list"):
        module.validate_proposal(
            {"path": "genesis/example.py", "new": "VALUE = 9"},
            "test-coder",
        )


def test_normalized_single_edit_still_obeys_protected_path_gate(tmp_path: Path) -> None:
    module = _module(tmp_path)
    with pytest.raises(RuntimeError):
        module.validate_proposal(
            {
                "path": "GENESIS_CONSTITUTION.md",
                "start_line": 1,
                "end_line": 1,
                "new": "changed",
            },
            "test-coder",
        )

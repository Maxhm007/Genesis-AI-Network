from __future__ import annotations

from pathlib import Path

import pytest

from genesis.coding import CodingModule


TARGET = "genesis/large_existing_target.py"


def _write_large_target(root: Path) -> Path:
    target = root / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from __future__ import annotations\n\n"
        + ("# retained repository history xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" * 1_100)
        + "VALUE = 1\n",
        encoding="utf-8",
    )
    assert target.stat().st_size > CodingModule.MAX_TOTAL_BYTES
    return target


def test_compact_edit_can_materialize_existing_file_larger_than_full_file_limit(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    coding = CodingModule(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    value_line = lines.index("VALUE = 1") + 1

    proposal = coding.validate_proposal(
        {
            "edits": [
                {
                    "path": TARGET,
                    "start_line": value_line,
                    "end_line": value_line,
                    "new": "VALUE = 2",
                }
            ]
        },
        "bounded-model-route",
    )

    rendered = proposal.files[TARGET]
    assert len(rendered.encode("utf-8")) > CodingModule.MAX_TOTAL_BYTES
    assert rendered.endswith("VALUE = 2\n")
    compile(rendered, TARGET, "exec")


def test_raw_full_file_proposal_still_respects_existing_total_byte_limit(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    coding = CodingModule(tmp_path)

    assert CodingModule.MAX_TOTAL_BYTES == 80_000
    with pytest.raises(ValueError, match="coding proposal exceeds byte limit"):
        coding.validate_proposal(
            {"files": {TARGET: target.read_text(encoding="utf-8")}},
            "bounded-model-route",
        )


def test_compact_edit_replacement_byte_limit_remains_enforced(tmp_path: Path) -> None:
    target = _write_large_target(tmp_path)
    coding = CodingModule(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    value_line = lines.index("VALUE = 1") + 1

    with pytest.raises(ValueError, match="coding proposal edits exceed byte limit"):
        coding.validate_proposal(
            {
                "edits": [
                    {
                        "path": TARGET,
                        "start_line": value_line,
                        "end_line": value_line,
                        "new": "X" * (CodingModule.MAX_EDIT_BYTES + 1),
                    }
                ]
            },
            "bounded-model-route",
        )

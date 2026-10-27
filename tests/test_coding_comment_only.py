from __future__ import annotations

from pathlib import Path

import pytest

from genesis.coding import CodingModule

SOURCE = "def summarize(rows):\n    total = len(rows)\n    return total\n"


def _module(tmp_path: Path) -> CodingModule:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "sample.py").write_text(SOURCE, encoding="utf-8")
    return CodingModule(tmp_path)


def _validate(module: CodingModule, after_line: int, new: str):
    proposal = {"edits": [{"path": "genesis/sample.py", "insert_after_line": after_line, "new": new}]}
    return module.validate_proposal(proposal, "test")


@pytest.mark.parametrize(
    "new",
    [
        "    # Add structured failure memory and strategy reuse prevention\n    # ...",
        '    """Summarize rows."""',
        "    'TODO: implement'",
        "    rows",
        "    f'{rows}'",
        "    if False:\n        pass",
    ],
)
def test_comment_or_placeholder_only_edit_is_rejected(tmp_path: Path, new: str) -> None:
    module = _module(tmp_path)
    with pytest.raises(ValueError, match="must change real code"):
        _validate(module, 1, new)


def test_range_edit_that_only_adds_a_trailing_comment_is_rejected(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = {"edits": [{"path": "genesis/sample.py", "start_line": 2, "end_line": 2, "new": "    total = len(rows)  # count rows"}]}
    with pytest.raises(ValueError, match="must change real code"):
        module.validate_proposal(proposal, "test")


def test_real_code_change_is_accepted(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = _validate(module, 2, "    # count only real rows\n    total = len([r for r in rows if r])")
    assert "len([r for r in rows if r])" in proposal.files["genesis/sample.py"]


def test_output_contract_says_comment_only_edits_are_rejected() -> None:
    assert "only adds comments" in CodingModule._output_contract()


def test_new_python_file_with_only_comments_is_rejected(tmp_path: Path) -> None:
    module = _module(tmp_path)
    proposal = {"files": {"genesis/new_helper.py": "# helper\n\"\"\"Docs.\"\"\"\n"}}
    with pytest.raises(ValueError, match="must change real code"):
        module.validate_proposal(proposal, "test")


def test_comment_only_python_plus_doc_line_is_rejected(tmp_path: Path) -> None:
    module = _module(tmp_path)
    (tmp_path / "docs").mkdir()
    proposal = {"files": {
        "genesis/sample.py": SOURCE.replace("    return total", "    # note\n    return total"),
        "docs/notes.md": "progress\n",
    }}
    with pytest.raises(ValueError, match="must change real code"):
        module.validate_proposal(proposal, "test")


def test_unparseable_existing_file_counts_as_change() -> None:
    from genesis.coding import _changes_code
    assert _changes_code("def broken(:\n", "VALUE = 1\n") is True

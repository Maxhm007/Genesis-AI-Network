from __future__ import annotations

import ast
from pathlib import Path

import pytest

from genesis.coding import CodingModule


def _module(tmp_path: Path, source: str, *, max_edits: int = 1) -> CodingModule:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "sample.py").write_text(source, encoding="utf-8")
    module = CodingModule(tmp_path)
    module.MAX_EDITS = max_edits
    return module


SOURCE = "def choose():\n    return 1\n\n\nVALUE = 1\nOTHER = 2\n"


def test_insert_adds_code_without_removing_the_sole_statement(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE)
    files = module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 1, "new": "value = 2"}])
    rendered = files["genesis/sample.py"]
    assert rendered.startswith("def choose():\n    value = 2\n    return 1\n")
    ast.parse(rendered)


def test_insert_at_top_and_end_of_file(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE, max_edits=2)
    files = module._files_from_edits([
        {"path": "genesis/sample.py", "insert_after_line": 0, "new": "import os"},
        {"path": "genesis/sample.py", "insert_after_line": 6, "new": "LAST = 3"},
    ])
    rendered = files["genesis/sample.py"]
    assert rendered.startswith("import os\ndef choose():")
    assert rendered.endswith("OTHER = 2\nLAST = 3\n")
    ast.parse(rendered)


def test_two_line_edits_in_one_file_both_apply(tmp_path: Path) -> None:
    # Before this change the second edit re-read the file and dropped the first.
    module = _module(tmp_path, SOURCE, max_edits=2)
    files = module._files_from_edits([
        {"path": "genesis/sample.py", "start_line": 5, "end_line": 5, "new": "VALUE = 10"},
        {"path": "genesis/sample.py", "start_line": 6, "end_line": 6, "new": "OTHER = 20"},
    ])
    rendered = files["genesis/sample.py"]
    assert "VALUE = 10\n" in rendered and "OTHER = 20\n" in rendered


def test_insert_and_replace_use_original_line_numbers(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE, max_edits=2)
    files = module._files_from_edits([
        {"path": "genesis/sample.py", "insert_after_line": 1, "new": "value = 2"},
        {"path": "genesis/sample.py", "start_line": 6, "end_line": 6, "new": "OTHER = 20"},
    ])
    rendered = files["genesis/sample.py"]
    assert "    value = 2\n    return 1\n" in rendered
    assert rendered.endswith("VALUE = 1\nOTHER = 20\n")


@pytest.mark.parametrize(
    "edits",
    [
        [{"start_line": 5, "end_line": 6, "new": "A = 1"}, {"start_line": 6, "end_line": 6, "new": "B = 1"}],
        [{"insert_after_line": 2, "new": "A = 1"}, {"insert_after_line": 2, "new": "B = 1"}],
    ],
)
def test_overlapping_edits_are_rejected(tmp_path: Path, edits: list[dict]) -> None:
    module = _module(tmp_path, SOURCE, max_edits=2)
    with pytest.raises(ValueError, match="overlap"):
        module._files_from_edits([{"path": "genesis/sample.py", **edit} for edit in edits])


def test_edit_count_limit_is_unchanged(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE)
    assert CodingModule.MAX_EDITS == 1
    with pytest.raises(ValueError, match="count out of bounds"):
        module._files_from_edits([
            {"path": "genesis/sample.py", "insert_after_line": 0, "new": "A = 1"},
            {"path": "genesis/sample.py", "insert_after_line": 6, "new": "B = 1"},
        ])


def test_sole_statement_guard_still_applies_with_several_edits(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE, max_edits=2)
    with pytest.raises(ValueError, match="only executable statement"):
        module._files_from_edits([
            {"path": "genesis/sample.py", "start_line": 2, "end_line": 2, "new": "# gone"},
            {"path": "genesis/sample.py", "start_line": 5, "end_line": 5, "new": "VALUE = 2"},
        ])


def test_empty_insert_and_mixed_shapes_are_rejected(tmp_path: Path) -> None:
    module = _module(tmp_path, SOURCE, max_edits=2)
    with pytest.raises(ValueError, match="non-empty"):
        module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 1, "new": "  "}])
    with pytest.raises(ValueError, match="do not mix"):
        module._files_from_edits([
            {"path": "genesis/sample.py", "old": "VALUE = 1", "new": "VALUE = 3"},
            {"path": "genesis/sample.py", "insert_after_line": 0, "new": "A = 1"},
        ])


def test_prompt_contract_mentions_insert(tmp_path: Path) -> None:
    assert "insert_after_line" in CodingModule._output_contract()


def _module_with(tmp_path, text):
    (tmp_path / "genesis").mkdir(exist_ok=True)
    (tmp_path / "genesis" / "sample.py").write_text(text, encoding="utf-8")
    return CodingModule(tmp_path)


def test_insert_with_line_range_is_rejected(tmp_path):
    module = _module_with(tmp_path, "A = 1\nB = 2\n")
    with pytest.raises(ValueError, match="both insert_after_line and start_line"):
        module._files_from_edits(
            [{"path": "genesis/sample.py", "insert_after_line": 1, "start_line": 1, "end_line": 2, "new": "C = 3"}]
        )


def test_insert_keeps_written_indentation_inside_block(tmp_path):
    module = _module_with(tmp_path, "def f(x):\n    if x:\n        y = 1\n    return x\n")
    files = module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 3, "new": "        z = 2"}])
    assert files["genesis/sample.py"] == "def f(x):\n    if x:\n        y = 1\n        z = 2\n    return x\n"


def test_insert_after_last_line_stays_top_level(tmp_path):
    module = _module_with(tmp_path, "try:\n    A = 1\nexcept Exception:\n    A = 0\n")
    files = module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 4, "new": "B = 2"}])
    assert files["genesis/sample.py"].endswith("    A = 0\nB = 2\n")


def test_insert_above_future_import_is_rejected(tmp_path):
    module = _module_with(tmp_path, '"""Doc."""\nfrom __future__ import annotations\nA = 1\n')
    with pytest.raises(ValueError, match="__future__"):
        module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 0, "new": "import os"}])
    files = module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 2, "new": "import os"}])
    assert "annotations\nimport os\n" in files["genesis/sample.py"]


@pytest.mark.parametrize("text", ["...", "pass"])
def test_insert_placeholder_is_rejected(tmp_path, text):
    module = _module_with(tmp_path, "A = 1\n")
    with pytest.raises(ValueError, match="placeholder"):
        module._files_from_edits([{"path": "genesis/sample.py", "insert_after_line": 1, "new": text}])
        
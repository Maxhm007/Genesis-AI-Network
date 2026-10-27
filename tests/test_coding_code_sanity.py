from __future__ import annotations

from pathlib import Path

import pytest

from genesis.coding import CodingModule, _code_sanity_problems

SOURCE = (
    "import os\n"
    "\n"
    "LIMIT = 3\n"
    "\n"
    "def summarize(rows):\n"
    "    total = len(rows)\n"
    "    for row in rows:\n"
    "        if not row:\n"
    "            continue\n"
    "    return total\n"
)


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
        "    assert decide_issue(fresh)",
        "    total = total + missing_name",
        "    if aged > LIMIT:\n        total = 0",
    ],
)
def test_new_undefined_name_is_rejected(tmp_path: Path, new: str) -> None:
    with pytest.raises(ValueError, match="undefined name"):
        _validate(_module(tmp_path), 6, new)


def test_code_after_return_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="can never run"):
        _validate(_module(tmp_path), 10, "    total = 0")


@pytest.mark.parametrize(
    "new",
    [
        "    total = total + LIMIT",
        "    extra = os.sep\n    total = total + len(extra)",
        "    total = sum(len(str(r)) for r in rows)",
        "    total = total if rows else len([])",
    ],
)
def test_defined_names_pass(tmp_path: Path, new: str) -> None:
    assert _validate(_module(tmp_path), 6, new) is not None


def test_existing_problems_are_not_blamed_on_new_edit() -> None:
    old = "def f():\n    return later_name\n"
    new = "def f():\n    value = 1\n    return later_name\n"
    assert _code_sanity_problems(old, new) == []


def test_syntax_error_and_star_import_are_left_to_other_checks() -> None:
    assert _code_sanity_problems("", "def f(:\n") == []
    assert _code_sanity_problems("", "from os import *\ndef f():\n    return sep\n") == []


def test_class_and_global_names_are_known() -> None:
    new = (
        "class A:\n    def m(self):\n        return A\n"
        "def g():\n    global COUNT\n    COUNT = 1\n"
        "def h():\n    return COUNT\n"
    )
    assert _code_sanity_problems("", new) == []

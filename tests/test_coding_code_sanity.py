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


def test_syntax_error_is_left_to_other_checks() -> None:
    assert _code_sanity_problems("", "def f(:\n") == []


def test_new_star_import_is_rejected_but_an_existing_one_is_kept() -> None:
    old = "def f():\n    return 1\n"
    new = "from os import *\ndef f():\n    return sep\n"
    assert any("import *" in p for p in _code_sanity_problems(old, new))
    assert _code_sanity_problems(new, new + "def g():\n    return sep\n") == []


@pytest.mark.parametrize(
    "new",
    [
        "class A:\n    def m(self):\n        fresh = 1\n        return fresh\n    def n(self):\n        return fresh\n",
        "if False:\n    fresh = None\ndef f():\n    return fresh\n",
        "g = lambda: (fresh := 1)\ndef f():\n    return fresh\n",
        "def f(rows):\n    if any(row for row in rows):\n        return row\n",
        "value = missing_name + 1\n",
        "class A:\n    size = missing_name\n",
        "names = [missing_name for _ in range(3)]\n",
    ],
)
def test_names_bound_only_elsewhere_are_rejected(new: str) -> None:
    assert any("undefined name" in p for p in _code_sanity_problems("", new))


def test_moving_dead_code_to_a_new_place_is_rejected() -> None:
    old = "def f():\n    return 1\n    x = 1\ndef g():\n    return 2\n"
    new = "def f():\n    return 1\ndef g():\n    return 2\n    y = 2\n"
    assert any("never run" in p for p in _code_sanity_problems(old, new))


@pytest.mark.parametrize(
    "new",
    [
        "class A:\n    def m(self):\n        return __class__\n",
        "where = __cached__\n",
        "def f[T](x: T) -> T:\n    return x\n",
        "class A:\n    size = 1\n    double = size * 2\n",
        "def f(rows):\n    if (n := len(rows)) > 1:\n        return n\n    return [y for x in rows if (y := x)]\n",
        "def outer():\n    v = 1\n    def inner():\n        nonlocal v\n        v = 2\n        return v\n    return inner\n",
        "try:\n    import json\nexcept ImportError:\n    json = None\n",
    ],
)
def test_valid_scoping_passes(new: str) -> None:
    assert _code_sanity_problems("", new) == []


def test_class_and_global_names_are_known() -> None:
    new = (
        "class A:\n    def m(self):\n        return A\n"
        "def g():\n    global COUNT\n    COUNT = 1\n"
        "def h():\n    return COUNT\n"
    )
    assert _code_sanity_problems("", new) == []


@pytest.mark.parametrize(
    "new",
    [
        "if not True:\n    fresh = None\ndef f():\n    return fresh\n",
        "if 0 == 1:\n    fresh = None\ndef f():\n    return fresh\n",
        "if True:\n    pass\nelse:\n    fresh = 1\nvalue = fresh\n",
        "for fresh in ():\n    pass\ndef f():\n    return fresh\n",
        "def f():\n    del fresh\n",
    ],
)
def test_bindings_that_never_happen_do_not_count(new: str) -> None:
    assert any("undefined name `fresh`" in p for p in _code_sanity_problems("", new))


def test_use_before_assignment_is_rejected() -> None:
    new = "def f():\n    x = fresh\n    fresh = 1\n    return x\n"
    assert any("before it is assigned" in p for p in _code_sanity_problems("", new))


@pytest.mark.parametrize(
    "new",
    [
        "def f(rows):\n    for r in rows:\n        if r:\n            print(prev)\n        prev = r\n",
        "def f():\n    x = 1\n    del x\n",
        "def f():\n    n = 0\n    n += 1\n    return n\n",
        "def f():\n    while True:\n        try:\n            v = 1\n        except Exception:\n            continue\n        return v\n",
        "def f(flag):\n    if flag:\n        v = 1\n    else:\n        v = 2\n    return v\n",
    ],
)
def test_valid_flow_passes(new: str) -> None:
    assert _code_sanity_problems("", new) == []


def test_renaming_a_function_with_existing_dead_code_passes() -> None:
    old = "def a():\n    return 1\n    x = 2\n"
    new = "def b():\n    return 1\n    x = 2\n"
    assert _code_sanity_problems(old, new) == []

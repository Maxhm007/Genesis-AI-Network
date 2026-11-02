from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis.coding import CodingModule


SOURCE = "def clamp(value):\n    return value\n"
EXISTING_TEST = "from genesis.sample import clamp\n\n\ndef test_clamp_keeps_small_values():\n    assert clamp(1) == 1\n"
FIX = {"path": "genesis/sample.py", "start_line": 2, "end_line": 2, "new": "    return min(value, 10)"}
NEW_TEST = "\n\ndef test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"


def _module(tmp_path: Path) -> CodingModule:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "sample.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(EXISTING_TEST, encoding="utf-8")
    return CodingModule(tmp_path)


def _proposal(*edits: dict) -> dict:
    return {"edits": list(edits)}


def test_test_first_mode_accepts_one_fix_plus_one_appended_test(tmp_path: Path) -> None:
    module = _module(tmp_path)
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST}
    proposal = module.validate_proposal(_proposal(FIX, test), "fake", require_regression_test=True)
    assert proposal.files["genesis/sample.py"] == "def clamp(value):\n    return min(value, 10)\n"
    assert proposal.files["tests/test_sample.py"].startswith(EXISTING_TEST)
    assert "def test_clamp_caps_large_values" in proposal.files["tests/test_sample.py"]


def test_test_first_mode_accepts_a_new_test_file(tmp_path: Path) -> None:
    module = _module(tmp_path)
    new_file = "from genesis.sample import clamp\n\n\ndef test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
    test = {"path": "tests/test_clamp_regression.py", "insert_after_line": 0, "new": new_file}
    proposal = module.validate_proposal(_proposal(FIX, test), "fake", require_regression_test=True)
    assert proposal.files["tests/test_clamp_regression.py"] == new_file


@pytest.mark.parametrize(
    ("edits", "message"),
    [
        ([FIX], "exactly two edits"),
        ([FIX, dict(FIX)], "one edit under tests/"),
        ([FIX, {"path": "tests/test_sample.py", "start_line": 5, "end_line": 5, "new": "    assert clamp(1) == 10"}], "insert_after_line only"),
        ([FIX, {"path": "tests/helpers.py", "insert_after_line": 0, "new": NEW_TEST}], "tests/test_*.py"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\nimport genesis.sample\ngenesis.sample.clamp = lambda v: 10\n"}], "non-test code"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\ndef test_x(v=print()):\n    assert clamp(50) == 10\n"}], "default values"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\ndef test_x():\n    clamp(50)\n"}], "asserts nothing"),
        ([FIX, {"path": "tests/test_new_regression.py", "insert_after_line": 3, "new": NEW_TEST}], "insert_after_line must be 0"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\n\ndef test_clamp_keeps_small_values():\n    assert clamp(50) == 10\n"}], "reuses the name `test_clamp_keeps_small_values`"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\nfrom genesis.sample import clamp as test_clamp_keeps_small_values\n\ndef test_y():\n    assert clamp(50) == 10\n"}], "reuses the name"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST + NEW_TEST}], "reuses the name `test_clamp_caps_large_values`"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\ndef test_x():\n    raises = clamp(50)\n"}], "asserts nothing"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\ndef test_x():\n    assert True\n    clamp(50)\n"}], "asserts nothing"),
        ([FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "\ndef test_x():\n    try:\n        v = clamp(50)\n    except NameError as e:\n        raise AssertionError(e)\n    assert v == 10\n"}], "try/except"),
        ([FIX, {"path": "tests/sub/test_x.py", "insert_after_line": 0, "new": NEW_TEST}], "tests/test_*.py"),
        ([FIX, {"path": "tests/test_../x.py", "insert_after_line": 0, "new": NEW_TEST}], "tests/test_*.py"),
    ],
)
def test_test_first_mode_rejects_unsafe_shapes(tmp_path: Path, edits: list[dict], message: str) -> None:
    module = _module(tmp_path)
    with pytest.raises(ValueError, match=message.replace("*", r"\*").replace("/", "/")):
        module.validate_proposal(_proposal(*edits), "fake", require_regression_test=True)


def test_test_first_mode_requires_a_real_fix_outside_tests(tmp_path: Path) -> None:
    module = _module(tmp_path)
    comment_only = {"path": "genesis/sample.py", "insert_after_line": 0, "new": "# clamp values"}
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST}
    with pytest.raises(ValueError, match="real code"):
        module.validate_proposal(_proposal(comment_only, test), "fake", require_regression_test=True)


def test_default_mode_still_allows_only_one_edit(tmp_path: Path) -> None:
    module = _module(tmp_path)
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST}
    with pytest.raises(ValueError, match="edits count out of bounds"):
        module.validate_proposal(_proposal(FIX, test), "fake")


class _Provider:
    name = "fake-test-first"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(_proposal(FIX, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST}))


def test_propose_asks_for_a_failing_test_first(tmp_path: Path) -> None:
    module = _module(tmp_path)
    provider = _Provider()
    proposal = module.propose("Clamp must cap large values at 10", ["genesis/sample.py"], provider=provider, require_regression_test=True)
    assert "TEST-FIRST" in provider.prompts[0] and "FAIL with an AssertionError" in provider.prompts[0]
    assert set(proposal.files) == {"genesis/sample.py", "tests/test_sample.py"}


def test_propose_default_prompt_is_unchanged(tmp_path: Path) -> None:
    module = _module(tmp_path)
    provider = _Provider()
    with pytest.raises(ValueError):
        module.propose("Clamp must cap large values at 10", ["genesis/sample.py"], provider=provider)
    assert all("TEST-FIRST" not in prompt for prompt in provider.prompts)


def test_test_first_mode_keeps_the_fix_inside_valid_paths(tmp_path: Path) -> None:
    module = _module(tmp_path)
    (tmp_path / "genesis" / "other.py").write_text("VALUE = 1\n", encoding="utf-8")

    class _Stray(_Provider):
        def reason(self, prompt: str) -> str:
            self.prompts.append(prompt)
            stray = {"path": "genesis/other.py", "start_line": 1, "end_line": 1, "new": "VALUE = 2"}
            return json.dumps(_proposal(stray, {"path": "tests/test_sample.py", "insert_after_line": 5, "new": NEW_TEST}))

    with pytest.raises(ValueError, match="VALID_PATHS"):
        module.propose("Clamp must cap large values at 10", ["genesis/sample.py"], provider=_Stray(), require_regression_test=True)


def test_test_first_mode_rejects_a_test_slid_under_an_existing_decorator(tmp_path: Path) -> None:
    module = _module(tmp_path)
    decorated = (
        "import pytest\nfrom genesis.sample import clamp\n\n\n@pytest.mark.parametrize('n', [1, 2])\n"
        "def test_clamp_keeps_small_values(n):\n    assert clamp(n) == n\n"
    )
    (tmp_path / "tests" / "test_sample.py").write_text(decorated, encoding="utf-8")
    # Inserting right after the decorator line hands the decorator to the new test.
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"}
    with pytest.raises(ValueError, match="changes an existing test"):
        module.validate_proposal(_proposal(FIX, test), "fake", require_regression_test=True)


def test_test_first_mode_allows_repeating_an_existing_import(tmp_path: Path) -> None:
    module = _module(tmp_path)
    again = "\nfrom genesis.sample import clamp\n\n\ndef test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": again}
    proposal = module.validate_proposal(_proposal(FIX, test), "fake", require_regression_test=True)
    assert "test_clamp_caps_large_values" in proposal.files["tests/test_sample.py"]


def test_test_first_mode_accepts_pytest_raises(tmp_path: Path) -> None:
    module = _module(tmp_path)
    raising = "\nimport pytest\n\n\ndef test_clamp_rejects_text():\n    with pytest.raises(TypeError):\n        clamp('x') + 1\n"
    test = {"path": "tests/test_sample.py", "insert_after_line": 5, "new": raising}
    module.validate_proposal(_proposal(FIX, test), "fake", require_regression_test=True)

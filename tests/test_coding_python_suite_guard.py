from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from genesis.coding import CodingModule


class SequenceProvider:
    name = "test-coding-provider"

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.responses.pop(0))


def _module(tmp_path: Path, source: str) -> CodingModule:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "sample.py").write_text(source, encoding="utf-8")
    return CodingModule(tmp_path)


def test_comment_only_edit_cannot_remove_sole_except_body(tmp_path: Path) -> None:
    module = _module(
        tmp_path,
        "def choose():\n"
        "    try:\n"
        "        return 1\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "    return 0\n",
    )

    with pytest.raises(ValueError, match="only executable statement"):
        module._apply_line_edit("genesis/sample.py", 5, 5, "# keep fallback documented")


def test_blank_edit_cannot_remove_sole_function_body(tmp_path: Path) -> None:
    module = _module(tmp_path, "def placeholder():\n    pass\n")

    with pytest.raises(ValueError, match="only executable statement"):
        module._apply_line_edit("genesis/sample.py", 2, 2, "")


def test_top_level_deletion_remains_allowed(tmp_path: Path) -> None:
    module = _module(tmp_path, "VALUE = 1\nOTHER = 2\n")

    rendered = module._apply_line_edit("genesis/sample.py", 1, 1, "")

    assert rendered == "OTHER = 2\n"
    ast.parse(rendered)


def test_replacing_parent_header_and_body_is_left_to_ast_validation(tmp_path: Path) -> None:
    module = _module(tmp_path, "def placeholder():\n    pass\n")

    rendered = module._apply_line_edit("genesis/sample.py", 1, 2, "VALUE = 1")

    assert rendered == "VALUE = 1\n"
    ast.parse(rendered)


def test_propose_retries_after_comment_only_sole_body_edit(tmp_path: Path) -> None:
    source = (
        "def choose():\n"
        "    try:\n"
        "        return 1\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "    return 0\n"
    )
    module = _module(tmp_path, source)
    provider = SequenceProvider(
        [
            {"edits": [{"path": "genesis/sample.py", "start_line": 5, "end_line": 5, "new": "# fallback"}]},
            {"edits": [{"path": "genesis/sample.py", "start_line": 5, "end_line": 5, "new": "return 0"}]},
        ]
    )

    proposal = module.propose(
        "Improve failure-aware fallback behavior.",
        ["genesis/sample.py"],
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "only executable statement" in provider.prompts[1]
    rendered = proposal.files["genesis/sample.py"]
    assert "        return 0\n" in rendered
    ast.parse(rendered)

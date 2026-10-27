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


def test_sole_body_rejection_names_range_and_statement(tmp_path: Path) -> None:
    module = _module(tmp_path, "def placeholder():\n    pass\n")

    with pytest.raises(ValueError) as caught:
        module._apply_line_edit("genesis/sample.py", 2, 2, "# todo")

    message = str(caught.value)
    assert "genesis/sample.py:2-2" in message
    assert "'pass'" in message
    assert "keep that statement" in message


def test_keeping_sole_statement_and_adding_code_beside_it_is_allowed(tmp_path: Path) -> None:
    module = _module(tmp_path, "def choose():\n    return 1\n")

    rendered = module._apply_line_edit("genesis/sample.py", 2, 2, "value = 1\nreturn value")

    ast.parse(rendered)
    assert "return value" in rendered


def test_prompt_allows_keeping_sole_body_statement(tmp_path: Path) -> None:
    module = _module(tmp_path, "def choose():\n    return 1\n")
    provider = SequenceProvider([{"edits": [{"path": "genesis/sample.py", "start_line": 2, "end_line": 2, "new": "return 2"}]}])

    module.propose("Return two.", ["genesis/sample.py"], provider=provider)

    assert "keep that statement in new" in provider.prompts[0]


def test_failed_proposal_keeps_the_rejected_change(tmp_path: Path) -> None:
    module = _module(tmp_path, "def placeholder():\n    pass\n")
    bad = {"edits": [{"path": "genesis/sample.py", "start_line": 2, "end_line": 2, "new": "# nothing"}]}
    provider = SequenceProvider([bad] * module.MAX_PROPOSAL_ATTEMPTS)

    with pytest.raises(ValueError) as caught:
        module.propose("Do something.", ["genesis/sample.py"], provider=provider)

    assert "# nothing" in getattr(caught.value, "rejected_change", "")

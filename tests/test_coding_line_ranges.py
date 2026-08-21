from pathlib import Path

import pytest

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


class LineRangeProvider:
    name = "line-range-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"edits":[{"path":"genesis/example.py","start_line":2,"end_line":2,"new":"VALUE = 8"}]}'


class PromptCaptureProvider(LineRangeProvider):
    name = "line-range-capture"

    def __init__(self) -> None:
        self.prompt = ""

    def reason(self, prompt: str) -> str:
        self.prompt = prompt
        return super().reason(prompt)


class SyntaxRetryProvider(LineRangeProvider):
    name = "syntax-retry-coder"

    def __init__(self) -> None:
        self.calls = 0

    def reason(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return '{"edits":[{"path":"genesis/example.py","start_line":2,"end_line":2,"new":"    return ="}]}'
        return '{"edits":[{"path":"genesis/example.py","start_line":2,"end_line":2,"new":"    return 2"}]}'


def test_line_range_edit_does_not_require_copying_old_text(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("HEADER = 1\nVALUE = 7\nTAIL = 3\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose(
        "Tune the value",
        ["genesis/example.py"],
        provider=LineRangeProvider(),
    )
    assert proposal.files["genesis/example.py"] == "HEADER = 1\nVALUE = 8\nTAIL = 3\n"


def test_prompt_exposes_numbered_context_and_forbids_old_text_copy(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("FIRST = 1\nSECOND = 2\n", encoding="utf-8")
    provider = PromptCaptureProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    module.propose("Tune one line", ["genesis/example.py"], provider=provider)
    assert "NUMBERED_CONTEXT" in provider.prompt
    assert "1|FIRST = 1" in provider.prompt
    assert "2|SECOND = 2" in provider.prompt
    assert "do NOT reproduce old source text" in provider.prompt
    assert "start_line" in provider.prompt
    assert "end_line" in provider.prompt


def test_line_range_rejects_out_of_bounds_target(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="exceeds file length"):
        module.validate_proposal(
            {"edits": [{"path": "genesis/example.py", "start_line": 2, "end_line": 2, "new": "VALUE = 8"}]},
            "test",
        )


def test_line_range_rejects_invalid_range(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="range is invalid"):
        module.validate_proposal(
            {"edits": [{"path": "genesis/example.py", "start_line": 2, "end_line": 1, "new": "VALUE = 8"}]},
            "test",
        )


def test_line_range_keeps_single_edit_and_protected_path_rules(tmp_path: Path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(RuntimeError):
        module.validate_proposal(
            {"edits": [{"path": "GENESIS_CONSTITUTION.md", "start_line": 1, "end_line": 1, "new": "changed"}]},
            "test",
        )


def test_invalid_python_edit_is_rejected_and_retried_inside_proposal(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    provider = SyntaxRetryProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.propose("Return two", ["genesis/example.py"], provider=provider)

    assert provider.calls == 2
    assert proposal.files["genesis/example.py"] == "def value():\n    return 2\n"

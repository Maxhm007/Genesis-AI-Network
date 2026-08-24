import ast
from pathlib import Path

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


class UnindentedExceptBodyProvider:
    name = "unindented-except-body-coder"

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.calls += 1
        return (
            '{"edits":[{"path":"genesis/example.py",'
            '"start_line":5,"end_line":5,"new":"return 2"}]}'
        )


def _write_example(root: Path) -> Path:
    target = root / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def choose():\n"
        "    try:\n"
        "        return 1\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "    return 0\n",
        encoding="utf-8",
    )
    return target


def test_python_line_edit_preserves_except_body_indentation(tmp_path: Path):
    _write_example(tmp_path)
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.validate_proposal(
        {
            "edits": [
                {
                    "path": "genesis/example.py",
                    "start_line": 5,
                    "end_line": 5,
                    "new": "return 2",
                }
            ]
        },
        "test-coder",
    )

    rendered = proposal.files["genesis/example.py"]
    assert "    except RuntimeError:\n        return 2\n" in rendered
    ast.parse(rendered)


def test_python_line_edit_preserves_relative_multiline_indentation(tmp_path: Path):
    _write_example(tmp_path)
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.validate_proposal(
        {
            "edits": [
                {
                    "path": "genesis/example.py",
                    "start_line": 5,
                    "end_line": 5,
                    "new": "if True:\n    return 2",
                }
            ]
        },
        "test-coder",
    )

    rendered = proposal.files["genesis/example.py"]
    assert "        if True:\n            return 2\n" in rendered
    ast.parse(rendered)


def test_propose_accepts_unindented_bounded_python_edit_without_retry(tmp_path: Path):
    _write_example(tmp_path)
    provider = UnindentedExceptBodyProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.propose(
        "Improve the fallback behavior inside choose without changing its structure",
        ["genesis/example.py"],
        provider=provider,
    )

    assert provider.calls == 1
    assert "        return 2\n" in proposal.files["genesis/example.py"]
    ast.parse(proposal.files["genesis/example.py"])

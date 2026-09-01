import json
from pathlib import Path

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry
from genesis.python_syntax_retry import _syntax_retry_guidance


class InteriorStatementRetryProvider:
    name = "interior-statement-retry-provider"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return json.dumps(
                {
                    "edits": [
                        {
                            "path": "genesis/example.py",
                            "start_line": 3,
                            "end_line": 3,
                            "new": "return 3",
                        }
                    ]
                }
            )
        assert "REJECTED_EDIT_RANGE: genesis/example.py:3-3" in prompt
        assert "AST_SAFE_STATEMENT_RANGE: genesis/example.py:2-5" in prompt
        assert "2|    config = {" in prompt
        assert "5|    }" in prompt
        assert "Do not edit only an interior line of this statement" in prompt
        return json.dumps(
            {
                "edits": [
                    {
                        "path": "genesis/example.py",
                        "start_line": 2,
                        "end_line": 5,
                        "new": 'config = {\n    "a": 1,\n    "b": 2,\n    "c": 3,\n}',
                    }
                ]
            }
        )


class DeterministicRepeatedSyntaxProvider:
    name = "deterministic-repeated-syntax-provider"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "FINAL_PYTHON_SYNTAX_RETRY:" in prompt:
            assert "PYTHON_SYNTAX_RETRY_ATTEMPT: 3/3" in prompt
            assert "Do not repeat the same path/range/replacement combination" in prompt
            return json.dumps(
                {
                    "edits": [
                        {
                            "path": "genesis/example.py",
                            "start_line": 2,
                            "end_line": 5,
                            "new": 'config = {\n    "a": 1,\n    "b": 2,\n    "c": 3,\n}',
                        }
                    ]
                }
            )
        return json.dumps(
            {
                "edits": [
                    {
                        "path": "genesis/example.py",
                        "start_line": 3,
                        "end_line": 3,
                        "new": "return 3",
                    }
                ]
            }
        )


def _write_example(root: Path) -> None:
    target = root / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def build():\n"
        "    config = {\n"
        '        "a": 1,\n'
        '        "b": 2,\n'
        "    }\n"
        "    return config\n",
        encoding="utf-8",
    )


def test_python_syntax_retry_uses_original_ast_statement_boundary(tmp_path: Path) -> None:
    _write_example(tmp_path)
    provider = InteriorStatementRetryProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.propose(
        "Add key c to the config while preserving valid Python structure",
        ["genesis/example.py"],
        provider=provider,
    )

    assert len(provider.prompts) == 2
    assert "PYTHON_SYNTAX_RETRY_ATTEMPT: 2/3" in provider.prompts[1]
    rendered = proposal.files["genesis/example.py"]
    assert '        "c": 3,' in rendered
    compile(rendered, "genesis/example.py", "exec")


def test_python_syntax_retry_changes_final_prompt_for_deterministic_provider(tmp_path: Path) -> None:
    _write_example(tmp_path)
    provider = DeterministicRepeatedSyntaxProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.propose(
        "Add key c to the config while preserving valid Python structure",
        ["genesis/example.py"],
        provider=provider,
    )

    assert len(provider.prompts) == 3
    assert "PYTHON_SYNTAX_RETRY_ATTEMPT: 2/3" in provider.prompts[1]
    assert "PYTHON_SYNTAX_RETRY_ATTEMPT: 3/3" in provider.prompts[2]
    assert "FINAL_PYTHON_SYNTAX_RETRY:" in provider.prompts[2]
    assert provider.prompts[1] != provider.prompts[2]
    rendered = proposal.files["genesis/example.py"]
    assert '        "c": 3,' in rendered
    compile(rendered, "genesis/example.py", "exec")


def test_python_syntax_retry_does_not_invent_structure_for_unparseable_provider_output(tmp_path: Path) -> None:
    _write_example(tmp_path)
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    guidance = _syntax_retry_guidance(
        module,
        "not-json",
        ValueError("coding proposal creates invalid Python syntax in genesis/example.py at 3:1: invalid syntax"),
    )

    assert guidance == ""

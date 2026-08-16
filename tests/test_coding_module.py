from pathlib import Path

import pytest

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


class FakeCodingProvider:
    name = "fake-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"title":"Add helper","rationale":"test","files":{"genesis/helper.py":"VALUE = 1\\n"}}'


def test_coding_module_prefers_non_bootstrap_provider(tmp_path: Path):
    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(FakeCodingProvider())
    module = CodingModule(tmp_path, registry)
    proposal = module.propose("Add a bounded helper")
    assert proposal.provider == "fake-coder"
    assert proposal.files["genesis/helper.py"] == "VALUE = 1\n"


def test_coding_module_rejects_protected_file(tmp_path: Path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(RuntimeError):
        module.validate_proposal(
            {
                "title": "bad",
                "files": {"GENESIS_CONSTITUTION.md": "changed"},
            },
            "test",
        )


def test_coding_module_rejects_path_traversal(tmp_path: Path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(RuntimeError):
        module.validate_proposal(
            {
                "title": "bad",
                "files": {"genesis/../run_genesis.py": "changed"},
            },
            "test",
        )


def test_coding_context_is_bounded_to_allowed_paths(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    context = module.read_context(["genesis/example.py"])
    assert context["genesis/example.py"] == "VALUE = 7\n"

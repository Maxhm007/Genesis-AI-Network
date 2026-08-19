from pathlib import Path
import importlib.util

import pytest

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


class FakeCodingProvider:
    name = "fake-coder"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"title":"Add helper","rationale":"test","files":{"genesis/helper.py":"VALUE = 1\\n"}}'


class WrappedCodingProvider(FakeCodingProvider):
    name = "wrapped-coder"

    def reason(self, prompt: str) -> str:
        return 'Here is the candidate:\n```json\n{"title":"Wrapped","rationale":"ok","files":{"genesis/wrapped.py":"VALUE = 2\\n"}}\n```\nDone.'


class RecoveringCodingProvider(FakeCodingProvider):
    name = "recovering-coder"

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            return '{"edits":['
        if self.calls == 2:
            return '{"title":"Still incomplete"}'
        return '{"edits":[{"path":"genesis/example.py","old":"VALUE = 7","new":"VALUE = 8"}]}'


class AlwaysBrokenCodingProvider(FakeCodingProvider):
    name = "always-broken-coder"

    def __init__(self) -> None:
        self.calls = 0

    def reason(self, prompt: str) -> str:
        self.calls += 1
        return '{"edits":['


class CompactEditProvider(FakeCodingProvider):
    name = "compact-edit-coder"

    def reason(self, prompt: str) -> str:
        return '{"edits":[{"path":"genesis/example.py","old":"VALUE = 7","new":"VALUE = 8"}]}'


class PromptCaptureProvider(CompactEditProvider):
    name = "prompt-capture-coder"

    def __init__(self) -> None:
        self.prompt = ""

    def reason(self, prompt: str) -> str:
        self.prompt = prompt
        return super().reason(prompt)


def _load_local_provider_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "local_reasoning_provider.py"
    spec = importlib.util.spec_from_file_location("genesis_local_reasoning_provider", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coding_module_prefers_non_bootstrap_provider(tmp_path: Path):
    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(FakeCodingProvider())
    module = CodingModule(tmp_path, registry)
    proposal = module.propose("Add a bounded helper")
    assert proposal.provider == "fake-coder"
    assert proposal.files["genesis/helper.py"] == "VALUE = 1\n"


def test_coding_module_extracts_balanced_json_from_wrapped_output(tmp_path: Path):
    provider = WrappedCodingProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose("Add wrapped helper", provider=provider)
    assert proposal.title == "Wrapped"
    assert proposal.files["genesis/wrapped.py"] == "VALUE = 2\n"


def test_coding_module_repairs_parse_and_schema_errors_with_same_provider(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    provider = RecoveringCodingProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose("Recover a malformed proposal", ["genesis/example.py"], provider=provider)
    assert proposal.files["genesis/example.py"] == "VALUE = 8\n"
    assert provider.calls == 3
    assert "RETRY:" in provider.prompts[1]
    assert "Exactly one edit" in provider.prompts[2]
    assert '"path":"genesis/example.py"' in provider.prompts[1]
    assert "existing allowed path" not in provider.prompts[1]


def test_coding_module_recovery_is_bounded(tmp_path: Path):
    provider = AlwaysBrokenCodingProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="after 3 bounded attempts"):
        module.propose("Never accept malformed output forever", provider=provider)
    assert provider.calls == module.MAX_PROPOSAL_ATTEMPTS


def test_coding_module_accepts_compact_exact_edit(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\nOTHER = 1\n", encoding="utf-8")
    provider = CompactEditProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose("Tune one value", ["genesis/example.py"], provider=provider)
    assert proposal.files["genesis/example.py"] == "VALUE = 8\nOTHER = 1\n"
    assert proposal.title == "Genesis bounded coding candidate"


def test_coding_prompt_requires_exactly_one_small_edit(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    provider = PromptCaptureProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    module.propose("Tune one value", ["genesis/example.py"], provider=provider)
    assert "exactly ONE smallest useful edit" in provider.prompt
    assert "no title/rationale/markdown/explanation" in provider.prompt
    assert '"path":"genesis/example.py"' in provider.prompt
    assert "existing allowed path" not in provider.prompt
    assert module.MAX_EDITS == 1
    assert module.MAX_CONTEXT_BYTES <= 12_000


def test_local_provider_compacts_large_prompt_without_losing_ends():
    provider_module = _load_local_provider_module()
    prompt = "RULES-AND-OBJECTIVE:" + ("A" * 20_000) + ":REPOSITORY-CONTEXT-END"
    compacted = provider_module.compact_prompt(prompt)
    assert len(compacted) < len(prompt)
    assert compacted.startswith("RULES-AND-OBJECTIVE:")
    assert compacted.endswith(":REPOSITORY-CONTEXT-END")
    assert len(compacted) <= provider_module.MAX_PROVIDER_PROMPT_CHARS + 40


def test_local_provider_output_budget_stays_bounded():
    provider_module = _load_local_provider_module()
    assert 256 <= provider_module.DEFAULT_MAX_NEW_TOKENS <= provider_module.MAX_ALLOWED_NEW_TOKENS <= 1024


def test_coding_module_rejects_multiple_compact_edits(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("A = 1\nB = 2\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="edits count out of bounds"):
        module.validate_proposal(
            {"edits": [
                {"path": "genesis/example.py", "old": "A = 1", "new": "A = 2"},
                {"path": "genesis/example.py", "old": "B = 2", "new": "B = 3"},
            ]},
            "test",
        )


def test_coding_module_rejects_ambiguous_compact_edit(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\nVALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="match exactly once"):
        module.validate_proposal(
            {"edits": [{"path": "genesis/example.py", "old": "VALUE = 7", "new": "VALUE = 8"}]},
            "test",
        )


def test_coding_module_rejects_protected_file(tmp_path: Path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(RuntimeError):
        module.validate_proposal({"files": {"GENESIS_CONSTITUTION.md": "changed"}}, "test")


def test_coding_module_rejects_path_traversal(tmp_path: Path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(RuntimeError):
        module.validate_proposal({"files": {"genesis/../run_genesis.py": "changed"}}, "test")


def test_coding_context_is_bounded_to_allowed_paths(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    context = module.read_context(["genesis/example.py"])
    assert context["genesis/example.py"] == "VALUE = 7\n"

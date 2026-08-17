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
            return '{"title":"Broken","rationale":"test","files":{"genesis/helper.py":"VALUE = 1\\n"}'
        if self.calls == 2:
            return '{"title":"Still incomplete","rationale":"test"}'
        return '{"title":"Recovered","rationale":"test","files":{"genesis/recovered.py":"VALUE = 3\\n"}}'


class AlwaysBrokenCodingProvider(FakeCodingProvider):
    name = "always-broken-coder"

    def __init__(self) -> None:
        self.calls = 0

    def reason(self, prompt: str) -> str:
        self.calls += 1
        return '{"title":"Broken"'


class CompactEditProvider(FakeCodingProvider):
    name = "compact-edit-coder"

    def reason(self, prompt: str) -> str:
        return '{"title":"Tune value","rationale":"small surgical change","edits":[{"path":"genesis/example.py","old":"VALUE = 7","new":"VALUE = 8"}]}'


class PromptCaptureProvider(FakeCodingProvider):
    name = "prompt-capture-coder"

    def __init__(self) -> None:
        self.prompt = ""

    def reason(self, prompt: str) -> str:
        self.prompt = prompt
        return '{"title":"Tune value","rationale":"small surgical change","edits":[{"path":"genesis/example.py","old":"VALUE = 7","new":"VALUE = 8"}]}'


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
    provider = RecoveringCodingProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose("Recover a malformed proposal", provider=provider)
    assert proposal.title == "Recovered"
    assert provider.calls == 3
    assert "RECOVERY:" in provider.prompts[1]
    assert "files mapping or compact edits list" in provider.prompts[2]


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


def test_coding_prompt_prefers_compact_surgical_edits(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\n", encoding="utf-8")
    provider = PromptCaptureProvider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    module.propose("Tune one value", ["genesis/example.py"], provider=provider)
    assert "preferably an edits list" in provider.prompt
    assert "faster and safer than reproducing whole files" in provider.prompt


def test_coding_module_rejects_ambiguous_compact_edit(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "genesis" / "example.py").write_text("VALUE = 7\nVALUE = 7\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    with pytest.raises(ValueError, match="match exactly once"):
        module.validate_proposal(
            {
                "title": "ambiguous",
                "edits": [{"path": "genesis/example.py", "old": "VALUE = 7", "new": "VALUE = 8"}],
            },
            "test",
        )


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

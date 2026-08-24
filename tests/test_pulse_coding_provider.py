from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_provider_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "pulse_coding_provider.py"
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location("genesis_pulse_coding_provider", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


def test_adaptive_coding_model_escalates_revision_prompts(monkeypatch):
    module = _load_provider_module()
    calls: list[tuple[str, str]] = []

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id
            self.max_new_tokens = max_new_tokens

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            calls.append((self.model_id, prompt))
            return self.model_id

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)

    assert model.reason("ROLE: bounded_coding_engineer\nOBJECTIVE: first pass") == "small-coder"
    assert model.reason("PREVIOUS_DEVELOPMENT_FEEDBACK: tests failed") == "strong-coder"
    assert model.reason("PREVIOUS_PIPELINE_FEEDBACK: repair failed") == "strong-coder"
    assert model.reason("RETRY: previous JSON was invalid") == "strong-coder"
    assert [model_id for model_id, _ in calls] == ["small-coder", "strong-coder", "strong-coder", "strong-coder"]


def test_adaptive_coding_model_falls_back_if_escalation_fails(monkeypatch):
    module = _load_provider_module()
    calls: list[str] = []

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id
            self.max_new_tokens = max_new_tokens

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            calls.append(self.model_id)
            if self.model_id == "strong-coder":
                raise RuntimeError("strong model unavailable")
            return "primary-result"

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)

    assert model.reason("PREVIOUS_DEVELOPMENT_FEEDBACK: tests failed") == "primary-result"
    assert calls == ["strong-coder", "small-coder"]


def test_adaptive_coding_model_can_disable_escalation(monkeypatch):
    module = _load_provider_module()

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id
            self.max_new_tokens = max_new_tokens

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            return self.model_id

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "", max_new_tokens=384)

    assert model.reason("PREVIOUS_DEVELOPMENT_FEEDBACK: tests failed") == "small-coder"

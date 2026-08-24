from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_provider_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "pulse_coding_provider.py"
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location("genesis_pulse_coding_runtime_provider", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


def test_escalation_model_has_own_compact_generation_budget(monkeypatch):
    module = _load_provider_module()
    constructed: list[tuple[str, int]] = []
    calls: list[tuple[str, int | None, int]] = []

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id
            constructed.append((model_id, max_new_tokens))

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            calls.append((self.model_id, max_new_tokens, len(prompt)))
            return self.model_id

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel(
        "small-coder",
        "strong-coder",
        max_new_tokens=384,
        escalation_max_new_tokens=128,
    )

    assert model.reason("RETRY: revise the candidate", max_new_tokens=256) == "strong-coder"
    assert constructed == [("strong-coder", 128)]
    assert calls == [("strong-coder", 128, len("RETRY: revise the candidate"))]


def test_escalation_prompt_is_compacted_without_dropping_tail(monkeypatch):
    module = _load_provider_module()
    prompts: list[str] = []

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            prompts.append(prompt)
            return self.model_id

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)
    long_prompt = "RETRY:\n" + ("A" * 9000) + "\nNUMBERED_CONTEXT: tail-evidence"

    assert model.reason(long_prompt) == "strong-coder"
    assert len(prompts[0]) <= module.ESCALATION_MAX_PROMPT_CHARS + 64
    assert "RETRY:" in prompts[0]
    assert "NUMBERED_CONTEXT: tail-evidence" in prompts[0]
    assert "escalation context elided" in prompts[0]


def test_noop_second_correction_reuses_base_prompt(monkeypatch):
    module = _load_provider_module()
    prompts: list[str] = []
    noop = '{"edits":[{"path":"genesis/coding.py","start_line":1,"end_line":1,"new":"same"}]}'
    base = (
        "ROLE: bounded_coding_engineer\n"
        "OBJECTIVE: change the implementation\n"
        'NUMBERED_CONTEXT: {"genesis/coding.py":"1|same"}\n'
    )

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            prompts.append(prompt)
            return noop

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)

    assert model.reason(base) == noop
    assert len(prompts) == 3
    assert prompts[1].count("PREVIOUS_NOOP:") == 1
    assert prompts[2].count("PREVIOUS_NOOP:") == 1
    assert "NOOP_CORRECTION_ATTEMPT: 2" in prompts[2]


def test_coding_workflow_precaches_both_configured_models_outside_request_timeout():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "coding-intelligence-pulse.yml").read_text(encoding="utf-8")

    assert "GENESIS_PULSE_ESCALATION_MODEL:" in workflow
    assert "Compute configured model cache key" in workflow
    assert "Prefetch configured coding models" in workflow
    assert "snapshot_download" in workflow
    assert "--escalation-model \"$GENESIS_PULSE_ESCALATION_MODEL\"" in workflow
    assert "--escalation-max-new-tokens 128" in workflow
    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS" in workflow

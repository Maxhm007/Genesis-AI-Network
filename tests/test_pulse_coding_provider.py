from __future__ import annotations

import importlib.util
import json
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


def _coding_prompt(line_text: str = "        return None") -> str:
    numbered = {"genesis/coding.py": f"1|class CodingModule:\n2|    def _provider(self):\n3|{line_text}"}
    return (
        "ROLE: bounded_coding_engineer\n"
        "OBJECTIVE: improve provider fallback reliability\n"
        f"NUMBERED_CONTEXT: {json.dumps(numbered, sort_keys=True)}\n"
    )


def test_noop_line_edit_is_corrected_inside_same_provider_call(monkeypatch):
    module = _load_provider_module()
    calls: list[tuple[str, str]] = []
    outputs = [
        json.dumps(
            {
                "edits": [
                    {
                        "path": "genesis/coding.py",
                        "start_line": 3,
                        "end_line": 3,
                        "new": "return None",
                    }
                ]
            }
        ),
        json.dumps(
            {
                "edits": [
                    {
                        "path": "genesis/coding.py",
                        "start_line": 3,
                        "end_line": 3,
                        "new": "return self.providers.available_providers()[0] if self.providers.available_providers() else None",
                    }
                ]
            }
        ),
    ]

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            calls.append((self.model_id, prompt))
            return outputs.pop(0)

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)

    result = model.reason(_coding_prompt())

    assert "available_providers" in result
    assert [model_id for model_id, _ in calls] == ["small-coder", "strong-coder"]
    assert "previous edit was a NO-OP" in calls[1][1]


def test_noop_correction_is_bounded(monkeypatch):
    module = _load_provider_module()
    calls: list[str] = []
    noop = json.dumps(
        {
            "edits": [
                {
                    "path": "genesis/coding.py",
                    "start_line": 3,
                    "end_line": 3,
                    "new": "return None",
                }
            ]
        }
    )

    class FakeLocalReasoningModel:
        def __init__(self, model_id: str, *, max_new_tokens: int) -> None:
            self.model_id = model_id

        def reason(self, prompt: str, max_new_tokens: int | None = None) -> str:
            calls.append(self.model_id)
            return noop

    monkeypatch.setattr(module, "LocalReasoningModel", FakeLocalReasoningModel)
    model = module.AdaptiveCodingModel("small-coder", "strong-coder", max_new_tokens=384)

    assert model.reason(_coding_prompt()) == noop
    assert calls == ["small-coder", "strong-coder", "strong-coder"]


def test_noop_detection_supports_legacy_identical_old_new():
    module = _load_provider_module()
    raw = json.dumps({"edits": [{"path": "genesis/coding.py", "old": "return None", "new": "return None"}]})

    assert module.AdaptiveCodingModel._is_noop_edit(_coding_prompt(), raw) is True


def test_noop_detection_accounts_for_python_indent_normalization():
    module = _load_provider_module()
    raw = json.dumps(
        {
            "edits": [
                {
                    "path": "genesis/coding.py",
                    "start_line": 3,
                    "end_line": 3,
                    "new": "return None",
                }
            ]
        }
    )

    assert module.AdaptiveCodingModel._is_noop_edit(_coding_prompt(), raw) is True


def test_noop_detection_preserves_meaningful_python_indentation_change():
    module = _load_provider_module()
    raw = json.dumps(
        {
            "edits": [
                {
                    "path": "genesis/coding.py",
                    "start_line": 3,
                    "end_line": 3,
                    "new": "    second()",
                }
            ]
        }
    )

    assert module.AdaptiveCodingModel._is_noop_edit(_coding_prompt("second()"), raw) is False


def test_noop_detection_preserves_nonpython_whitespace_change():
    module = _load_provider_module()
    numbered = {"docs/note.md": "1|item"}
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        "OBJECTIVE: indent a nested Markdown item\n"
        f"NUMBERED_CONTEXT: {json.dumps(numbered, sort_keys=True)}\n"
    )
    raw = json.dumps(
        {
            "edits": [
                {
                    "path": "docs/note.md",
                    "start_line": 1,
                    "end_line": 1,
                    "new": "    item",
                }
            ]
        }
    )

    assert module.AdaptiveCodingModel._is_noop_edit(prompt, raw) is False


def test_full_file_noop_detection_does_not_strip_whitespace():
    module = _load_provider_module()
    numbered = {"docs/note.md": "1|item"}
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        "OBJECTIVE: preserve formatting evidence\n"
        f"NUMBERED_CONTEXT: {json.dumps(numbered, sort_keys=True)}\n"
    )
    raw = json.dumps({"files": {"docs/note.md": " item"}})

    assert module.AdaptiveCodingModel._is_noop_edit(prompt, raw) is False

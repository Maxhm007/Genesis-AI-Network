from __future__ import annotations

import json

from genesis.evolution_learning import ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


def _item(summary: str, title: str = "quantization capability") -> ResearchItem:
    return ResearchItem(
        fingerprint="f" * 64,
        source="test",
        title=title,
        summary=summary,
        url="https://example.invalid/research",
        published_at="2026-08-21T00:00:00Z",
    )


class _Provider:
    name = "test-provider"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def test_pulse_learning_prompt_is_compact() -> None:
    engine = object.__new__(PulseEvolutionLearningEngine)
    prompt = engine._prompt(
        _item("A" * 5000),
        [("genesis/example.py", "B" * PulseEvolutionLearningEngine.MAX_PULSE_TARGET_BYTES)],
    )

    assert "A" * PulseEvolutionLearningEngine.MAX_PULSE_LEARNING_BYTES in prompt
    assert "A" * (PulseEvolutionLearningEngine.MAX_PULSE_LEARNING_BYTES + 1) not in prompt
    assert len(prompt) < 4000


def test_pulse_learning_skips_unrelated_targets_without_model(tmp_path) -> None:
    source = tmp_path / "genesis" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def alpha():\n    return 'unrelated'\n", encoding="utf-8")

    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path

    assert engine._catalog(_item("quantization kernels and tensor packing")) == []


def test_pulse_catalog_requires_more_than_one_weak_token_overlap(tmp_path) -> None:
    source = tmp_path / "genesis" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def choose_device():\n    return 'cpu'\n", encoding="utf-8")

    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path

    assert engine._catalog(_item("device projection memory mapping")) == []


def test_pulse_extracts_grounded_transferable_lesson_without_release_assets() -> None:
    summary = (
        "<details open> Clamp the final tensor tile to the remaining valid K range so the kernel "
        "does not read beyond the tensor extent. This prevents corrupted results on unaligned inputs. "
        "</details> **Website:** <https://example.invalid> **Linux:** [binary](https://example.invalid/bin)"
    )
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": "Bound the final processing tile to the remaining valid data extent.",
            "evidence": "Clamp the final tensor tile to the remaining valid K range",
            "topics": ["bounds checking", "tensor tails"],
            "confidence": 0.91,
            "reason": "",
        }
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(_item(summary))

    assert result["decision"] == "learn"
    assert result["confidence_normalized"] == 0.91
    assert "Website" not in provider.prompts[0]
    assert "binary" not in provider.prompts[0]
    assert result["lesson_evidence"] in summary


def test_pulse_rejects_hallucinated_research_lesson() -> None:
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": "Use speculative decoding for every request.",
            "evidence": "This exact evidence is not in the research source.",
            "topics": ["decoding"],
            "confidence": 99,
            "reason": "",
        }
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(
        _item("A release fixes a bounded tensor tail read on unaligned inputs.")
    )

    assert result["decision"] == "skip"
    assert result["reason"] == "ungrounded_learning_lesson"


def test_pulse_rejects_source_specific_feature_as_transferable_lesson() -> None:
    summary = (
        "mtmd: add --mmproj-device argument (#23255) and retain the "
        "MTMD_BACKEND_DEVICE environment variable for compatibility"
    )
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": "Add a command-line argument to specify the projection device for MTMD.",
            "evidence": "mtmd: add --mmproj-device argument (#23255)",
            "topics": ["command-line arguments", "device selection"],
            "confidence": 0.9,
            "reason": "",
        }
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(_item(summary, title="MTMD device support"))

    assert result["decision"] == "skip"
    assert result["reason"] == "source_specific_learning_lesson"
    assert "MTMD" in result["source_specific_markers"]

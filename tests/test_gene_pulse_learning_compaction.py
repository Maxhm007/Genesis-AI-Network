from __future__ import annotations

from genesis.evolution_learning import ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


def _item(summary: str) -> ResearchItem:
    return ResearchItem(
        fingerprint="f" * 64,
        source="test",
        title="quantization capability",
        summary=summary,
        url="https://example.invalid/research",
        published_at="2026-08-21T00:00:00Z",
    )


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

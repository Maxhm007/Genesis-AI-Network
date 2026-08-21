from __future__ import annotations

import json

from genesis.evolution_learning import ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


def _item(
    summary: str,
    title: str = "quantization capability",
    source: str = "test",
) -> ResearchItem:
    return ResearchItem(
        fingerprint="f" * 64,
        source=source,
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


class _SequenceProvider:
    name = "test-provider"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payloads.pop(0))


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


def test_pulse_extracts_grounded_source_evidence_without_release_assets() -> None:
    summary = (
        "<details open> Clamp the final tensor tile to the remaining valid K range so the kernel "
        "does not read beyond the tensor extent. This prevents corrupted results on unaligned inputs. "
        "</details> **Website:** <https://example.invalid> **Linux:** [binary](https://example.invalid/bin)"
    )
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(_item(summary))

    assert result["decision"] == "learn"
    assert result["confidence_normalized"] == engine.DIRECT_ROUTING_CONFIDENCE
    assert provider.prompts == []
    assert result["lesson_evidence"] in summary
    assert "tensor" in result["lesson_evidence"].lower()
    assert "Website" not in result["technical_source"]
    assert "binary" not in result["technical_source"]
    assert "model_runtime" in result["capability_domains"]


def test_pulse_anchors_direct_lesson_to_exact_source_text() -> None:
    summary = (
        "Large Language Models increasingly require selective removal of harmful knowledge. "
        "We argue that effective unlearning must operate at the level of concepts, ensuring complete removal "
        "of unsafe applications while maintaining benign and beneficial knowledge."
    )
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(
        _item(summary, title="Concept-sensitive unlearning", source="arxiv")
    )

    assert result["decision"] == "learn"
    assert result["lesson_evidence"] in summary
    assert "unlearning" in result["lesson_evidence"].lower()
    assert result["lesson_evidence_overlap"] >= 1
    assert "memory_learning" in result["capability_domains"]
    assert provider.prompts == []


def test_provider_cannot_inject_hallucinated_research_lesson() -> None:
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": "Use speculative decoding for every request.",
            "topics": ["speculative decoding"],
            "confidence": 99,
        }
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(
        _item("A release fixes a bounded tensor tail read on unaligned inputs.")
    )

    assert result["decision"] == "learn"
    assert "speculative decoding" not in result["lesson"].lower()
    assert result["lesson_evidence"] in _item(
        "A release fixes a bounded tensor tail read on unaligned inputs."
    ).summary
    assert provider.prompts == []


def test_source_specific_feature_is_preserved_as_evidence_not_model_instruction() -> None:
    summary = (
        "mtmd: add --mmproj-device argument (#23255) and retain the "
        "MTMD_BACKEND_DEVICE environment variable for compatibility with command-line device selection"
    )
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(_item(summary, title="MTMD device support"))

    assert result["decision"] == "learn"
    assert result["lesson_evidence"] in summary
    assert provider.prompts == []


def test_pulse_unfamiliar_arxiv_becomes_emerging_capability_without_provider() -> None:
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(
        _item(
            "We derive exact variational identities for nonnegative martingales at arbitrary random times.",
            title="Information on trajectories and martingales",
            source="arxiv",
        )
    )

    assert result["decision"] == "learn"
    assert result["capability_domains"] == ["emerging_capability"]
    assert provider.prompts == []


def test_pulse_unfamiliar_rf_research_becomes_emerging_capability_without_provider() -> None:
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider

    result = engine._extract_lesson(
        _item(
            "We compare ceiling-mounted FMCW, IR-UWB, and Wi-Fi sensing using synchronized recordings. "
            "All technologies are evaluated with the same convolutional neural network for human activity "
            "recognition and sleep monitoring across room layouts.",
            title="Comparison of radio technologies for in-bedroom activity monitoring",
            source="arxiv",
        )
    )

    assert result["decision"] == "learn"
    assert result["capability_domains"] == ["emerging_capability"]
    assert provider.prompts == []


def test_pulse_keeps_confidence_research_in_reliability_domain() -> None:
    provider = _Provider({"decision": "skip"})
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.provider = provider
    summary = (
        "Post-hoc confidence estimation gives users a signal for deciding when a prediction can be trusted. "
        "The method improves failure prediction by separating incorrect predictions from reliable predictions."
    )

    result = engine._extract_lesson(
        _item(summary, title="Margin-controlled confidence estimation", source="arxiv")
    )

    assert result["decision"] == "learn"
    assert "reliability_evaluation" in result["capability_domains"]
    assert provider.prompts == []


def test_pulse_domain_catalog_only_exposes_shared_executable_targets(tmp_path) -> None:
    genesis = tmp_path / "genesis"
    genesis.mkdir(parents=True)
    (genesis / "gene_learning.py").write_text(
        "class GeneLearningEngine:\n"
        "    def add_lesson(self, knowledge):\n"
        "        return knowledge\n",
        encoding="utf-8",
    )
    runtime = genesis / "provider_runtime.py"
    runtime.write_text(
        "class ModelInferenceRuntime:\n"
        "    def decode_token(self, token):\n"
        "        return token\n",
        encoding="utf-8",
    )

    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path
    item = _item(
        "Use quantization during language model inference and token decoding.",
        title="Efficient LLM inference",
    )

    catalog = engine._catalog_for_domains(item, ["model_runtime"])

    assert [path for path, _ in catalog] == ["genesis/provider_runtime.py"]


def test_pulse_mapping_uses_exact_source_and_code_anchors_without_provider(tmp_path) -> None:
    target = tmp_path / "genesis" / "memory_policy.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        '"""Concept unlearning safety policy preserving benign knowledge."""\n'
        "def retention_policy():\n"
        "    return 'preserve benign concepts'\n",
        encoding="utf-8",
    )
    summary = (
        "Effective unlearning must operate at the level of concepts. "
        "Unsafe applications should be removed while benign and beneficial knowledge is maintained."
    )
    provider = _SequenceProvider(
        [
            {"decision": "skip"},
            {"decision": "skip"},
        ]
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path
    engine.provider = provider

    finding = engine._assess(
        _item(summary, title="Concept-level unlearning benchmark", source="arxiv")
    )

    assert finding["decision"] == "upgrade"
    assert finding["learning_evidence"] in summary
    assert finding["target_evidence"] in target.read_text(encoding="utf-8")
    assert finding["grounded"] is True
    assert finding["shared_capability_domains"] == ["memory_learning"]
    assert finding["routing_mode"] == "direct_source_evidence"
    assert provider.prompts == []

from __future__ import annotations

from genesis.evolution_learning import EvolutionLearningStore, ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


class _ExplodingProvider:
    name = "must-not-be-called"

    def __init__(self) -> None:
        self.calls = 0

    def reason(self, prompt: str) -> str:
        self.calls += 1
        raise AssertionError("research intake must not call a reasoning provider")


def _item(*, fingerprint: str = "a" * 64) -> ResearchItem:
    return ResearchItem(
        fingerprint=fingerprint,
        source="arxiv",
        title="Resolution-aware physical support estimation",
        summary=(
            "Adaptive endpoint bracketing evaluates only candidates that can still affect the physical report "
            "and otherwise safely coarsens or abstains. The method avoids unsupported refinement with fewer "
            "candidate evaluations."
        ),
        url="https://example.invalid/emerging-capability",
        published_at="2026-08-21T00:00:00Z",
    )


def _release_fragment(*, fingerprint: str = "b" * 64) -> ResearchItem:
    return ResearchItem(
        fingerprint=fingerprint,
        source="github:ggml-org/llama.cpp",
        title="b10590",
        summary=(
            "<details open> vendor : update subprocess.h (#27409) </details> "
            "**Website:** - <https://llama.app> **Attestations:** release artifacts"
        ),
        url="https://github.com/ggml-org/llama.cpp/releases/tag/b10590",
        published_at="2026-08-23T08:20:51Z",
    )


def _known_domain_release(*, fingerprint: str = "c" * 64) -> ResearchItem:
    return ResearchItem(
        fingerprint=fingerprint,
        source="github:huggingface/transformers",
        title="v5.15.1",
        summary=(
            "Transformer inference fixes token device mismatch during decoding and tensor placement (#47877). "
            "The runtime now keeps candidate tokens aligned with the selected inference device."
        ),
        url="https://github.com/huggingface/transformers/releases/tag/v5.15.1",
        published_at="2026-08-22T20:13:48Z",
    )


def _engine(tmp_path, provider: _ExplodingProvider | None = None) -> PulseEvolutionLearningEngine:
    genesis = tmp_path / "genesis"
    genesis.mkdir(parents=True, exist_ok=True)
    (genesis / "learned_capabilities.py").write_text(
        "def register_capability():\n"
        "    return True\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path
    engine.provider = provider
    return engine


def test_unknown_domain_becomes_new_capability_without_provider(tmp_path) -> None:
    provider = _ExplodingProvider()
    engine = _engine(tmp_path, provider)

    finding = engine._assess(_item())

    assert finding["decision"] == "upgrade"
    assert finding["new_capability"] is True
    assert finding["target_path"] == "genesis/learned_capabilities.py"
    assert finding["fallback_from"] == "no_existing_capability_domain"
    assert "emerging_capability" in finding["capability_domains"]
    assert finding["lesson_evidence"] in _item().summary
    assert provider.calls == 0


def test_extract_lesson_is_direct_source_evidence(tmp_path) -> None:
    provider = _ExplodingProvider()
    engine = _engine(tmp_path, provider)

    lesson = engine._extract_lesson(_item())

    assert lesson["decision"] == "learn"
    assert lesson["routing_mode"] == "direct_source_evidence"
    assert lesson["lesson_evidence"] in _item().summary
    assert lesson["confidence_normalized"] == engine.DIRECT_ROUTING_CONFIDENCE
    assert provider.calls == 0


def test_product_release_fragment_without_capability_evidence_is_skipped(tmp_path) -> None:
    provider = _ExplodingProvider()
    engine = _engine(tmp_path, provider)

    lesson = engine._extract_lesson(_release_fragment())
    finding = engine._assess(_release_fragment(fingerprint="d" * 64))

    assert lesson["decision"] == "skip"
    assert lesson["reason"] == "release_fragment_not_transferable"
    assert finding["decision"] == "skip"
    assert finding["reason"] == "release_fragment_not_transferable"
    assert provider.calls == 0


def test_known_capability_release_is_not_blocked_by_fragment_gate(tmp_path) -> None:
    provider = _ExplodingProvider()
    engine = _engine(tmp_path, provider)

    lesson = engine._extract_lesson(_known_domain_release())

    assert lesson["decision"] == "learn"
    assert "model_runtime" in lesson["capability_domains"]
    assert provider.calls == 0


def test_emerging_domain_never_fakes_existing_target_match(tmp_path) -> None:
    engine = _engine(tmp_path)

    domains = engine._target_domains(
        "genesis/example.py",
        "def calculate_endpoint_bracketing(value):\n    return value\n",
    )

    assert "emerging_capability" not in domains


def test_prior_evaluated_items_are_replayed_exactly_once(tmp_path) -> None:
    store = EvolutionLearningStore(tmp_path)
    first = _item(fingerprint="1" * 64)
    second = _item(fingerprint="2" * 64)
    store.ingest([first, second])
    store.set_research_status(first.fingerprint, "evaluated")
    store.set_research_status(second.fingerprint, "evaluated")

    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.store = store

    assert engine._replay_evaluated_for_new_capability_policy() == 2
    assert store.research_queue_summary()["counts"]["pending"] == 2
    assert engine._replay_evaluated_for_new_capability_policy() == 0
    assert store.meta_get(engine.POLICY_REPLAY_META_KEY) == "done"


def test_waiting_and_quarantined_provider_failures_replay_for_direct_routing(tmp_path) -> None:
    store = EvolutionLearningStore(tmp_path)
    waiting = _item(fingerprint="3" * 64)
    quarantined = _item(fingerprint="4" * 64)
    evaluated = _item(fingerprint="5" * 64)
    store.ingest([waiting, quarantined, evaluated])
    store.set_research_status(waiting.fingerprint, "waiting")
    store.set_research_status(quarantined.fingerprint, "quarantined")
    store.set_research_status(evaluated.fingerprint, "evaluated")

    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.store = store

    assert engine._replay_provider_failures_for_direct_routing() == 3
    assert store.research_queue_summary()["counts"]["pending"] == 3
    assert engine._replay_provider_failures_for_direct_routing() == 0
    assert store.meta_get(engine.DIRECT_ROUTING_REPLAY_META_KEY) == "done"

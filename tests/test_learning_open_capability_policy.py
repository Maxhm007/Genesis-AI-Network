from __future__ import annotations

import json

from genesis.evolution_learning import EvolutionLearningStore, ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


class _Provider:
    name = "test-provider"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def _item(*, fingerprint: str = "a" * 64) -> ResearchItem:
    return ResearchItem(
        fingerprint=fingerprint,
        source="arxiv",
        title="Resolution-aware physical support inference",
        summary=(
            "Adaptive endpoint bracketing evaluates only candidates that can still affect the physical report "
            "and otherwise safely coarsens or abstains. The method avoids unsupported refinement with fewer "
            "candidate evaluations."
        ),
        url="https://example.invalid/emerging-capability",
        published_at="2026-08-21T00:00:00Z",
    )


def _engine(tmp_path, provider: _Provider) -> PulseEvolutionLearningEngine:
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


def test_unknown_domain_can_become_new_capability(tmp_path) -> None:
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": (
                "Adaptive endpoint bracketing can reduce candidate evaluations while preserving safe abstention "
                "when refinement is unsupported."
            ),
            "topics": ["adaptive endpoint bracketing", "candidate evaluations", "safe abstention"],
            "confidence": 0.9,
            "reason": "",
        }
    )
    engine = _engine(tmp_path, provider)

    finding = engine._assess(_item())

    assert finding["decision"] == "upgrade"
    assert finding["new_capability"] is True
    assert finding["target_path"] == "genesis/learned_capabilities.py"
    assert finding["fallback_from"] == "no_relevant_genesis_target"
    assert "emerging_capability" in finding["capability_domains"]
    assert len(provider.prompts) == 1


def test_emerging_domain_never_fakes_existing_target_match(tmp_path) -> None:
    provider = _Provider({})
    engine = _engine(tmp_path, provider)

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

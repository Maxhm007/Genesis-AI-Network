from __future__ import annotations

import json

from genesis.evolution_learning import ResearchItem
from scripts.gene_pulse import PulseEvolutionLearningEngine


class _Provider:
    name = "test-provider"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def _item(summary: str) -> ResearchItem:
    return ResearchItem(
        fingerprint="a" * 64,
        source="arxiv",
        title="Agent tool-use learning",
        summary=summary,
        url="https://example.invalid/agent-tool-use",
        published_at="2026-08-21T00:00:00Z",
    )


def test_verified_unmapped_lesson_becomes_new_capability(tmp_path) -> None:
    genesis = tmp_path / "genesis"
    genesis.mkdir(parents=True)
    (genesis / "learned_capabilities.py").write_text(
        "def register_capability():\n"
        "    return True\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )
    summary = (
        "General tool use by agents improves when training explicitly teaches tool affordances, "
        "argument grounding, tool-call workflows, and recovery from incomplete information."
    )
    provider = _Provider(
        {
            "decision": "learn",
            "lesson": "Agent tool use improves when learning explicitly covers tool affordances and grounded workflows.",
            "topics": ["agent", "tool use", "learning", "grounding"],
            "confidence": 0.9,
            "reason": "",
        }
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path
    engine.provider = provider

    finding = engine._assess(_item(summary))

    assert finding["decision"] == "upgrade"
    assert finding["new_capability"] is True
    assert finding["target_path"] == "genesis/learned_capabilities.py"
    assert finding["target_evidence"] == "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT"
    assert finding["learning_evidence"] in summary
    assert finding["fallback_from"] == "no_relevant_genesis_target"
    assert len(provider.prompts) == 1


def test_new_capability_fallback_keeps_upgrade_confidence_gate(tmp_path) -> None:
    genesis = tmp_path / "genesis"
    genesis.mkdir(parents=True)
    (genesis / "learned_capabilities.py").write_text(
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )
    engine = object.__new__(PulseEvolutionLearningEngine)
    engine.root = tmp_path

    finding = engine._new_capability_finding(
        {
            "lesson": "A weakly supported agent lesson.",
            "lesson_evidence": "weak evidence",
            "topics": ["agent"],
            "confidence_normalized": 0.6,
            "capability_domains": ["agent_reasoning"],
        },
        planner_reason="no_relevant_genesis_target",
    )

    assert finding["decision"] == "skip"
    assert finding["reason"] == "new_capability_confidence_below_threshold"

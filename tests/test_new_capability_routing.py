from __future__ import annotations

import json
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.autonomy_pipeline import PipelineStore
from genesis.evolution_learning import GenesisEvolutionLearningEngine, ResearchItem
from genesis.modules.task_queue import PersistentTaskQueue


class PlannerProvider:
    name = "test-capability-planner"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "genesis").mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)
    (root / "genesis" / "learned_capabilities.py").write_text(
        "from __future__ import annotations\n\n"
        "def register_capability(name, description, evidence, handler):\n"
        "    return (name, description, evidence, handler)\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )
    # Fill the catalog with unrelated files to prove the capability incubator is
    # deliberately included instead of relying on accidental lexical ranking.
    for index in range(12):
        (root / "genesis" / f"module_{index}.py").write_text(
            f"def module_{index}():\n    return 'unrelated'\n",
            encoding="utf-8",
        )
    return root


def _item() -> ResearchItem:
    return ResearchItem(
        fingerprint="abc123",
        source="github:ggml-org/llama.cpp",
        title="MTMD runtime device selection",
        summary="mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
        url="https://example.invalid/release",
        published_at="2026-08-22T00:00:00+00:00",
    )


def _engine(root: Path, provider: PlannerProvider) -> GenesisEvolutionLearningEngine:
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    pipeline = PipelineStore(queue.path)
    return GenesisEvolutionLearningEngine(
        root,
        queue=queue,
        pipeline=pipeline,
        provider=provider,
        research_fetcher=lambda: ([], []),
    )


def test_planner_can_identify_grounded_new_capability(tmp_path: Path) -> None:
    root = _root(tmp_path)
    provider = PlannerProvider(
        {
            "decision": "upgrade",
            "kind": "new_capability",
            "target_path": "genesis/learned_capabilities.py",
            "capability_key": "runtime_device_selection",
            "lesson": "Select an explicit supported runtime device while keeping a fallback.",
            "lesson_topics": ["model_runtime", "device_selection"],
            "summary": "Add bounded runtime device selection as a new executable Genesis capability.",
            "acceptance": "Given requested and available devices, select a supported requested device or deterministic fallback.",
            "learning_evidence": "mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
            "target_evidence": "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT",
            "confidence": 0.93,
        }
    )
    engine = _engine(root, provider)

    finding = engine._assess(_item())

    assert finding["decision"] == "upgrade"
    assert finding["new_capability"] is True
    assert finding["target_path"] == "genesis/learned_capabilities.py"
    assert finding["capability_key"] == "runtime_device_selection"
    assert finding["grounded"] is True
    assert "new_capability" in provider.prompts[0]
    catalog = engine._catalog(_item())
    assert catalog[0][0] == "genesis/learned_capabilities.py"


def test_new_capability_enqueue_uses_shared_development_pipeline(tmp_path: Path) -> None:
    root = _root(tmp_path)
    provider = PlannerProvider({"decision": "skip", "summary": "unused"})
    engine = _engine(root, provider)
    finding = {
        "decision": "upgrade",
        "kind": "new_capability",
        "new_capability": True,
        "grounded": True,
        "target_path": "genesis/learned_capabilities.py",
        "capability_key": "runtime_device_selection",
        "lesson": "Select an explicit supported runtime device while keeping a fallback.",
        "lesson_evidence": "mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
        "lesson_topics": ["model_runtime"],
        "summary": "Add bounded runtime device selection.",
        "acceptance": "Select supported request or fallback deterministically.",
        "learning_evidence": "mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
        "target_evidence": "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT",
        "confidence_normalized": 0.93,
    }

    result = engine._enqueue(_item(), finding)
    task = engine.queue.get(result["task_id"])
    record = engine.pipeline.get(result["task_id"])

    assert result["status"] == "new_capability_enqueued"
    assert result["capability_key"] == "runtime_device_selection"
    assert result["capability_generation"] == 1
    assert task is not None
    assert task.payload["source"] == "genesis.evolution_learning"
    assert task.payload["task_type"] == "new_capability"
    assert task.payload["capability_key"] == "runtime_device_selection"
    assert task.payload["target_path"] == "genesis/learned_capabilities.py"
    assert task.payload["discovery"]["finding"]["new_capability"] is True
    assert record is not None
    assert record.stage == "discovered"


def test_ungrounded_new_capability_is_skipped(tmp_path: Path) -> None:
    root = _root(tmp_path)
    provider = PlannerProvider(
        {
            "decision": "upgrade",
            "kind": "new_capability",
            "target_path": "genesis/learned_capabilities.py",
            "capability_key": "invented_capability",
            "lesson": "Invent an ability with no source support.",
            "summary": "Invent an ability.",
            "acceptance": "Something happens.",
            "learning_evidence": "this exact evidence does not exist",
            "target_evidence": "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT",
            "confidence": 0.99,
        }
    )
    engine = _engine(root, provider)

    finding = engine._assess(_item())

    assert finding["decision"] == "skip"
    assert finding["reason"] == "ungrounded_upgrade_proposal"


def test_failure_learning_transfers_across_capability_generations(tmp_path: Path) -> None:
    root = _root(tmp_path)
    loop = AutonomousEngineeringLoop(root)
    first = loop.queue.create(
        "Build capability generation one",
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "capability_key": "runtime_device_selection",
            "capability_generation": 1,
        },
        max_attempts=1,
    )
    loop.queue.transition(first.task_id, "assigned", module_id="genesis.coding")
    quarantined = loop.queue.record_failure(
        first.task_id,
        "review rejected fallback behavior because unsupported devices were not bounded",
        classification="internal_development_review",
        retry_after_seconds=0,
        module_id="genesis.coding",
    )
    assert quarantined.state == "quarantined"

    second = loop.queue.create(
        "Build capability generation two",
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "capability_key": "runtime_device_selection",
            "capability_generation": 2,
        },
        max_attempts=4,
    )

    context = loop._failure_learning_context(second)

    assert quarantined.task_id in context
    assert "unsupported devices were not bounded" in context
    assert '"capability_key": "runtime_device_selection"' in context
    assert '"capability_generation": 1' in context

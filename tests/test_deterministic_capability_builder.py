from __future__ import annotations

import json
from pathlib import Path

from genesis.autonomous_engineering import AutonomousEngineeringLoop
from genesis.modules.task_queue import PersistentTaskQueue
from genesis.providers import ProviderRegistry
from genesis.selfdev import SelfDevResult


class TrackingQwenProvider:
    name = "qwen2.5-coder-1.5b-gene-pulse"

    def __init__(self, payload: dict | None = None) -> None:
        self.calls = 0
        self.payload = payload

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.calls += 1
        if self.payload is None:
            raise AssertionError("Qwen must not be called when deterministic learned-capability coding applies")
        return json.dumps(self.payload)


def _write_learned_target(root: Path) -> None:
    path = root / "genesis" / "learned_capabilities.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from __future__ import annotations\n\n"
        "def register_capability(name, description, evidence, handler):\n"
        "    return (name, description, evidence, handler)\n\n"
        "# GENESIS_LEARNED_CAPABILITY_INSERTION_POINT\n",
        encoding="utf-8",
    )


def _learning_task(
    root: Path,
    *,
    lesson: str,
    evidence: str,
    objective: str = "Autonomously apply one bounded learned capability upgrade.",
):
    queue = PersistentTaskQueue(root / "runtime" / "genesis_tasks.sqlite3")
    task = queue.create(
        objective,
        module_id="genesis.coding",
        payload={
            "source": "genesis.evolution_learning",
            "target_path": "genesis/learned_capabilities.py",
            "context_paths": ["genesis/learned_capabilities.py"],
            "task_type": "self_upgrade",
            "learning": {
                "fingerprint": "f92ab6ae15c781c0fda71bdb4c64a6add52b362971b212aa9e8069100739059d",
                "source": "github:ggml-org/llama.cpp",
            },
            "discovery": {
                "finding": {
                    "decision": "upgrade",
                    "grounded": True,
                    "new_capability": True,
                    "lesson": lesson,
                    "lesson_evidence": evidence,
                    "lesson_topics": ["model_runtime"],
                }
            },
        },
        max_attempts=4,
    )
    return queue, task


def _pass_candidate(loop: AutonomousEngineeringLoop, captured: dict) -> None:
    def fake_execute(proposal):
        captured["proposal"] = proposal
        return SelfDevResult(
            branch="genesis/candidate-test",
            candidate_id="test",
            tests_passed=True,
            committed=True,
            changed_files=("genesis/learned_capabilities.py",),
            commit_sha="abc123",
            message="candidate",
        )

    loop.coding.execute_candidate = fake_execute
    loop.security.write_report = lambda *args, **kwargs: {"status": "pass", "findings": []}


def test_grounded_device_learning_builds_candidate_without_qwen(tmp_path: Path) -> None:
    _write_learned_target(tmp_path)
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    queue, task = _learning_task(
        tmp_path,
        lesson="Add a command-line argument to specify the memory-mapped projection device for MTMD.",
        evidence="mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
    )
    loop.queue = queue

    captured = {}
    _pass_candidate(loop, captured)

    attempt = loop._attempt_task(task, tmp_path / "runtime")

    assert qwen.calls == 0
    assert attempt["coding_status"] == "candidate_created"
    assert attempt["coding_strategy"] == "deterministic_learned_capability"
    proposal = captured["proposal"]
    assert proposal.provider == "genesis-deterministic-capability-builder"
    rendered = proposal.files["genesis/learned_capabilities.py"]
    assert "runtime_device_selection_f92ab6ae15c7" in rendered
    assert "MTMD_BACKEND_DEVICE" in rendered
    current = queue.get(task.task_id)
    assert current is not None
    assert current.state == "review"


def test_grounded_device_learning_retries_after_pipeline_feedback_without_qwen(tmp_path: Path) -> None:
    _write_learned_target(tmp_path)
    qwen = TrackingQwenProvider()
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    queue, task = _learning_task(
        tmp_path,
        lesson="Add a command-line argument to specify the memory-mapped projection device for MTMD.",
        evidence="mtmd: add --mmproj-device argument and keep the MTMD_BACKEND_DEVICE fallback.",
        objective=(
            "Autonomously apply one bounded learned capability upgrade.\n\n"
            "PREVIOUS_PIPELINE_FEEDBACK: unrelated repository baseline tests failed after the prior candidate."
        ),
    )
    loop.queue = queue

    captured = {}
    _pass_candidate(loop, captured)

    attempt = loop._attempt_task(task, tmp_path / "runtime")

    assert qwen.calls == 0
    assert attempt["coding_status"] == "candidate_created"
    assert attempt["coding_strategy"] == "deterministic_learned_capability"
    assert "runtime_device_selection_f92ab6ae15c7" in captured["proposal"].files["genesis/learned_capabilities.py"]


def test_grounded_unknown_template_waits_without_non_qwen_provider(tmp_path: Path) -> None:
    _write_learned_target(tmp_path)
    qwen = TrackingQwenProvider({"edits": []})
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    queue, task = _learning_task(
        tmp_path,
        lesson="Exact variational identities can support a bounded identity transform.",
        evidence="Verified source evidence describes the transform but has no deterministic Genesis template.",
    )
    loop.queue = queue

    attempt = loop._attempt_task(task, tmp_path / "runtime")

    assert qwen.calls == 0
    assert attempt["coding_status"] == "waiting_for_coding_provider"
    assert attempt["error"] == "no_non_qwen_coding_provider_available"
    assert attempt["provider_policy"] == "grounded_agentic_capability_non_qwen_only"
    assert attempt["capability_scope"] == "append_only_learned_capability"
    current = queue.get(task.task_id)
    assert current is not None
    assert current.state == "paused"
    assert current.attempt_count == 0


def test_ungrounded_new_capability_still_blocks_qwen_invention(tmp_path: Path) -> None:
    _write_learned_target(tmp_path)
    qwen = TrackingQwenProvider({"edits": []})
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(qwen)
    loop = AutonomousEngineeringLoop(tmp_path, registry)
    queue, task = _learning_task(
        tmp_path,
        lesson="Speculative capability idea.",
        evidence="Unverified claim.",
    )
    task.payload["discovery"]["finding"]["grounded"] = False
    loop.queue = queue

    attempt = loop._attempt_task(task, tmp_path / "runtime")

    assert qwen.calls == 0
    assert attempt["coding_status"] == "waiting_for_coding_provider"
    assert attempt["provider_policy"] == "ungrounded_capability_requires_stronger_provider"
    current = queue.get(task.task_id)
    assert current is not None
    assert current.state == "paused"
    assert current.attempt_count == 0
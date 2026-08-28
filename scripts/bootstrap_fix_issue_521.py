from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_if_needed(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"expected patch context not found in {path}")
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one patch context in {path}, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_grounding_gate() -> None:
    path = ROOT / "genesis" / "autonomous_engineering.py"
    old = '''            context_paths = self._context_paths_for_task(task)\n            attempt["context_paths"] = context_paths\n            provider = DeterministicLearnedCapabilityProvider.for_task(self.root, task, self.coding)\n            if provider is None:\n                provider = self._coding_provider()\n            if provider is None:\n                self.queue.pause(task.task_id, "waiting_for_eligible_coding_provider")\n                attempt["coding_status"] = "waiting_for_coding_provider"\n                attempt["error"] = "no_eligible_coding_provider_available"\n                return attempt\n\n            attempt["coding_strategy"] = (\n                "deterministic_learned_capability"\n                if provider.name == DeterministicLearnedCapabilityProvider.name\n                else "external_non_qwen_provider"\n            )\n'''
    new = '''            context_paths = self._context_paths_for_task(task)\n            attempt["context_paths"] = context_paths\n\n            finding = ((task.payload.get("discovery") or {}).get("finding") or {})\n            new_capability = bool(finding.get("new_capability"))\n            grounded_capability = finding.get("grounded") is True\n            if new_capability and not grounded_capability:\n                self.queue.pause(task.task_id, "waiting_for_grounded_capability_evidence")\n                attempt["coding_status"] = "waiting_for_coding_provider"\n                attempt["provider_policy"] = "ungrounded_capability_requires_grounded_evidence"\n                attempt["capability_scope"] = "append_only_learned_capability"\n                attempt["error"] = "grounded_evidence_required_before_capability_generation"\n                return attempt\n\n            provider = DeterministicLearnedCapabilityProvider.for_task(self.root, task, self.coding)\n            if provider is None:\n                provider = self._coding_provider()\n                if new_capability and grounded_capability:\n                    attempt["capability_scope"] = "append_only_learned_capability"\n                    attempt["provider_policy"] = (\n                        "grounded_agentic_capability_qwen_preferred"\n                        if provider is not None and self._is_qwen_provider(provider)\n                        else "grounded_agentic_capability_validated_provider"\n                    )\n            if provider is None:\n                self.queue.pause(task.task_id, "waiting_for_eligible_coding_provider")\n                attempt["coding_status"] = "waiting_for_coding_provider"\n                attempt["error"] = "no_eligible_coding_provider_available"\n                return attempt\n\n            attempt["coding_strategy"] = (\n                "deterministic_learned_capability"\n                if provider.name == DeterministicLearnedCapabilityProvider.name\n                else "external_qwen_provider"\n                if self._is_qwen_provider(provider)\n                else "external_non_qwen_provider"\n            )\n'''
    replace_if_needed(path, old, new)


def patch_single_lane_tests() -> None:
    path = ROOT / "tests" / "test_adaptive_pulse_scheduler.py"
    replace_if_needed(path, "def test_autorepair_preserves_immediate_refill_and_five_lane_capacity() -> None:\n", "def test_autorepair_preserves_immediate_refill_and_single_lane_capacity() -> None:\n")
    replace_if_needed(path, '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'5\'" in text\n', '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'1\'" in text\n')

    path = ROOT / "tests" / "test_github_issue_autorepair_heartbeat_workflow.py"
    replace_if_needed(path, "def test_heartbeat_preserves_five_lane_capacity_and_queue_filters() -> None:\n", "def test_heartbeat_preserves_single_lane_capacity_and_queue_filters() -> None:\n")
    replace_if_needed(path, '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'5\'" in text\n', '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'1\'" in text\n')
    replace_if_needed(
        path,
        '    assert "github-issue-autorepair-worker.yml" not in text\n    assert "github-issue-autorepair-integration.yml" not in text\n',
        '    assert "gh workflow run github-issue-autorepair-worker.yml" not in text\n    assert "gh workflow run github-issue-autorepair-integration.yml" not in text\n',
    )

    path = ROOT / "tests" / "test_github_issue_autorepair_integration_transaction.py"
    replace_if_needed(path, "def test_parallel_solver_capacity_is_preserved() -> None:\n", "def test_single_solver_capacity_is_preserved() -> None:\n")
    replace_if_needed(path, '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'5\'" in text\n', '    assert "GENESIS_ISSUE_REPAIR_MAX_PARALLEL: \'1\'" in text\n')


if __name__ == "__main__":
    patch_grounding_gate()
    patch_single_lane_tests()
    print("Issue #521 bootstrap patches applied.")

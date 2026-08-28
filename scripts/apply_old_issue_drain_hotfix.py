from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected source block not found: {label}")
    return text.replace(old, new, 1)


def patch_autonomous_engineering() -> None:
    path = ROOT / "genesis" / "autonomous_engineering.py"
    text = path.read_text(encoding="utf-8")
    old = '''    @staticmethod
    def _is_qwen_provider(provider) -> bool:
        """Qwen remains available to non-coding specialists, never to code execution."""
        return "qwen" in str(getattr(provider, "name", "")).strip().lower()

    def _coding_provider(self):
        """Return the best available non-Qwen, non-bootstrap coding provider.

        The small local Qwen runtime is useful for bounded discovery/review tasks,
        but it must not be a blocking implementation dependency. Coding either
        uses another eligible provider or checkpoints without consuming repair
        budget.
        """
        candidates = []
        for provider in self.providers.available_providers():
            profile = IntelligenceRouter.profile(provider)
            if profile.name == "genesis-bootstrap" or self._is_qwen_provider(provider):
                continue
            if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            candidates.append((profile.resource_cost, -profile.reliability, profile.name, provider))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3]
'''
    new = '''    @staticmethod
    def _is_qwen_provider(provider) -> bool:
        """Return whether a provider is from the local Qwen family."""
        return "qwen" in str(getattr(provider, "name", "")).strip().lower()

    def _coding_provider(self):
        """Return the best eligible coder, preferring non-Qwen but allowing Qwen fallback.

        A locally available Qwen model must not deadlock autonomous repair when it
        is the only trained coding/reasoning provider. Non-Qwen providers remain
        preferred when available. Every generated candidate still has to pass the
        normal repository tests, Security inspection, and independent validators
        before promotion, so model fallback never bypasses quality or safety gates.
        """
        candidates = []
        for provider in self.providers.available_providers():
            profile = IntelligenceRouter.profile(provider)
            if profile.name == "genesis-bootstrap":
                continue
            if "coding" not in profile.capabilities and "reasoning" not in profile.capabilities:
                continue
            qwen_fallback = 1 if self._is_qwen_provider(provider) else 0
            candidates.append(
                (qwen_fallback, profile.resource_cost, -profile.reliability, profile.name, provider)
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return candidates[0][4]
'''
    text = replace_once(text, old, new, "coding provider policy")
    text = replace_once(
        text,
        '"provider_policy": "qwen_excluded_from_coding",',
        '"provider_policy": "prefer_non_qwen_qwen_validated_fallback",',
        "provider policy evidence",
    )
    text = replace_once(
        text,
        'self.queue.pause(task.task_id, "waiting_for_non_qwen_coding_provider")',
        'self.queue.pause(task.task_id, "waiting_for_eligible_coding_provider")',
        "provider wait reason",
    )
    text = replace_once(
        text,
        'attempt["error"] = "no_non_qwen_coding_provider_available"',
        'attempt["error"] = "no_eligible_coding_provider_available"',
        "provider wait error",
    )
    path.write_text(text, encoding="utf-8")


def patch_efficient_engineering() -> None:
    path = ROOT / "genesis" / "efficient_engineering.py"
    text = path.read_text(encoding="utf-8")
    old = '''    @staticmethod
    def _github_issue_fairness_key(task) -> tuple:
        """Order Issue work so older untouched issues run once, then retries rotate fairly."""
        issue_number = int(task.payload.get("github_issue_number") or 0)
        generation = int(task.payload.get("work_generation") or 1)
        untouched_first_generation = generation == 1 and task.attempt_count == 0 and task.state == "new"
        if untouched_first_generation:
            return (0, issue_number, task.created_at, task.task_id)
        return (1, task.updated_at, issue_number, generation, task.task_id)
'''
    new = '''    @staticmethod
    def _github_issue_fairness_key(task) -> tuple:
        """Keep an Issue's age across generations so newer Issues cannot starve it.

        Priority-100 work is an emergency lane. All other Issue-backed engineering
        is ordered by GitHub Issue number first, which is monotonic creation order
        inside one repository. A retry generation therefore retains the age of its
        Issue instead of becoming younger than every newly created first generation.
        """
        issue_number = int(task.payload.get("github_issue_number") or 0)
        generation = int(task.payload.get("work_generation") or 1)
        emergency_lane = 0 if int(task.priority) >= 100 else 1
        return (
            emergency_lane,
            issue_number,
            task.updated_at,
            generation,
            task.attempt_count,
            task.task_id,
        )
'''
    text = replace_once(text, old, new, "GitHub Issue fairness key")
    text = replace_once(
        text,
        "for task in self.queue.list(state=state, limit=100):",
        "for task in self.queue.list(state=state, limit=5000):",
        "Issue candidate scan limit",
    )
    path.write_text(text, encoding="utf-8")


def write_regression_tests() -> None:
    path = ROOT / "tests" / "test_old_issue_drain_regression.py"
    path.write_text(
        '''from __future__ import annotations

from pathlib import Path

from genesis.efficient_engineering import EfficientAutonomousEngineeringLoop


def _issue_task(loop, key: str, issue: int, *, generation: int = 1, priority: int = 95):
    task, _ = loop.queue.create_unique(
        key,
        f"Resolve GitHub issue #{issue}.",
        module_id="genesis.self_development",
        priority=priority,
        payload={
            "task_type": "github_issue_development",
            "github_issue_number": issue,
            "work_generation": generation,
        },
    )
    return task


def test_old_issue_keeps_age_across_retry_generations(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    old = _issue_task(loop, "old-109-generation-5", 109, generation=5)
    _issue_task(loop, "new-348-generation-1", 348, generation=1)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == old.task_id
    assert loop._selection_trace[-1]["reason"] == "github_issue_fair_rotation"


def test_priority_100_emergency_can_preempt_old_issue(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    _issue_task(loop, "old-normal-109", 109, generation=5, priority=95)
    emergency = _issue_task(loop, "new-critical-500", 500, generation=1, priority=100)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == emergency.task_id


def test_old_issue_is_visible_beyond_legacy_top_100_priority_window(tmp_path: Path):
    loop = EfficientAutonomousEngineeringLoop(tmp_path)
    old = _issue_task(loop, "old-visible-109", 109, generation=5, priority=90)
    for number in range(300, 425):
        _issue_task(loop, f"newer-{number}", number, generation=1, priority=96)
    selected = loop._select_task()
    assert selected is not None
    assert selected.task_id == old.task_id
''',
        encoding="utf-8",
    )


def main() -> None:
    patch_autonomous_engineering()
    patch_efficient_engineering()
    write_regression_tests()
    print("old issue drain hotfix applied to working tree")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path

from genesis.adaptive_learning import AdaptiveLearningEngine, LearningAwareAITeam, OutcomeLearningStore
from genesis.adaptive_team import PerformanceAdaptiveAITeam


class DummyProvider:
    def __init__(self, name: str) -> None:
        self.name = name


class DummyRegistry:
    def available_providers(self):
        return []


def test_outcome_store_ranks_measured_provider_performance(tmp_path: Path):
    store = OutcomeLearningStore(tmp_path / "adaptive.sqlite3")
    store.record(
        task_ref="t1",
        domain="engineering",
        agent="engineer",
        provider="strong",
        success=1.0,
        quality=1.0,
        evidence_weight=2.0,
        source="review:a",
    )
    store.record(
        task_ref="t2",
        domain="engineering",
        agent="engineer",
        provider="weak",
        success=0.0,
        quality=0.0,
        evidence_weight=2.0,
        source="review:b",
    )
    ranked = store.provider_scores(domain="engineering")
    assert [row["provider"] for row in ranked] == ["strong", "weak"]
    assert ranked[0]["score"] > ranked[1]["score"]


def test_outcome_store_deduplicates_same_evidence(tmp_path: Path):
    store = OutcomeLearningStore(tmp_path / "adaptive.sqlite3")
    kwargs = dict(
        task_ref="t1",
        domain="research",
        agent="researcher",
        provider="p1",
        success=1.0,
        quality=0.8,
        source="review:file.json",
    )
    assert store.record(**kwargs) is True
    assert store.record(**kwargs) is False
    assert len(store.list()) == 1


def test_adaptive_engine_ingests_explicit_review_quality(tmp_path: Path):
    runtime = tmp_path / "runtime"
    reviews = runtime / "task_reviews"
    reviews.mkdir(parents=True)
    (reviews / "task-1.json").write_text(
        json.dumps(
            {
                "task": {"task_id": "task-1", "objective": "fix failing code"},
                "quality_score": 0.9,
                "team_outputs": [
                    {"agent": "engineer", "provider": "p1", "status": "completed", "output": "patch"},
                    {"agent": "reviewer", "provider": "p2", "status": "error", "error": "failed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = AdaptiveLearningEngine(tmp_path).run_once()
    assert result["new_outcomes"] == 2
    preferences = json.loads((runtime / "learning_preferences.json").read_text(encoding="utf-8"))
    assert preferences["domains"]["engineering"]["providers"][0]["provider"] == "p1"
    assert "validate factual lessons" in preferences["rule"]


def test_learning_aware_team_prefers_ranked_provider(tmp_path: Path):
    preferences = tmp_path / "learning_preferences.json"
    preferences.write_text(
        json.dumps(
            {
                "overall": {"providers": []},
                "domains": {
                    "engineering": {
                        "providers": [
                            {"provider": "p2", "score": 0.9},
                            {"provider": "p1", "score": 0.5},
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    team = LearningAwareAITeam(DummyRegistry(), preferences_path=preferences)
    team._current_domain = "engineering"
    ordered = team._preferred_providers([DummyProvider("p1"), DummyProvider("p2")])
    assert [provider.name for provider in ordered] == ["p2", "p1"]


def test_performance_team_preserves_engineering_safety_roles(tmp_path: Path):
    preferences = tmp_path / "learning_preferences.json"
    preferences.write_text(
        json.dumps(
            {
                "domains": {
                    "engineering": {
                        "agents": [
                            {"agent": "scientist", "score": 0.99, "samples": 20},
                            {"agent": "engineer", "score": 0.20, "samples": 20},
                            {"agent": "reviewer", "score": 0.10, "samples": 20},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    team = PerformanceAdaptiveAITeam(DummyRegistry(), preferences_path=preferences, max_roles_per_task=4)
    plan = team.plan_task("fix failing code")
    assert plan.role_names[:3] == ("planner", "engineer", "reviewer")
    assert "scientist" in plan.role_names


def test_performance_team_ignores_single_sample_agent_rank(tmp_path: Path):
    preferences = tmp_path / "learning_preferences.json"
    preferences.write_text(
        json.dumps(
            {
                "domains": {
                    "engineering": {
                        "agents": [
                            {"agent": "scientist", "score": 1.0, "samples": 1}
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    team = PerformanceAdaptiveAITeam(DummyRegistry(), preferences_path=preferences, max_roles_per_task=4)
    plan = team.plan_task("fix failing code")
    assert plan.role_names == ("planner", "engineer", "reviewer")
    assert "insufficient repeated agent evidence" in plan.reason


def test_performance_team_keeps_validator_even_if_ranked_low(tmp_path: Path):
    preferences = tmp_path / "learning_preferences.json"
    preferences.write_text(
        json.dumps(
            {
                "domains": {
                    "validation": {
                        "agents": [
                            {"agent": "scientist", "score": 0.99, "samples": 10},
                            {"agent": "validator", "score": 0.01, "samples": 10}
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    team = PerformanceAdaptiveAITeam(DummyRegistry(), preferences_path=preferences, max_roles_per_task=4)
    plan = team.plan_task("validate candidate promotion")
    assert plan.role_names[:3] == ("planner", "validator", "reviewer")

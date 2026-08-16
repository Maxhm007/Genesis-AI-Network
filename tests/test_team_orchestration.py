from genesis.providers import ProviderRegistry
from genesis.team import AITeam


def test_simple_communication_uses_small_bounded_team():
    team = AITeam(ProviderRegistry(include_bootstrap=True))
    plan = team.plan_task("Respond to user: hello", "This is a communication request.")
    assert "planner" in plan.role_names
    assert len(plan.role_names) <= 3
    assert "scientist" not in plan.role_names
    assert "network_steward" not in plan.role_names


def test_research_task_selects_research_and_review_roles():
    team = AITeam(ProviderRegistry(include_bootstrap=True))
    plan = team.plan_task("Research evidence about cellular senescence and longevity")
    assert "researcher" in plan.role_names
    assert "reviewer" in plan.role_names
    assert len(plan.role_names) <= 4


def test_code_fix_selects_engineer_and_reviewer():
    team = AITeam(ProviderRegistry(include_bootstrap=True))
    plan = team.plan_task("Fix a failing Python test in the repair module")
    assert "engineer" in plan.role_names
    assert "reviewer" in plan.role_names


def test_non_bootstrap_provider_is_preferred_for_team_work():
    class StrongProvider:
        name = "strong"
        def available(self): return True
        def reason(self, prompt): return "ok"

    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(StrongProvider())
    team = AITeam(registry)
    outputs = team.run_task("Respond to user: hello", "communication request")
    assert outputs
    assert all(item.get("provider") == "strong" for item in outputs if item["status"] == "completed")

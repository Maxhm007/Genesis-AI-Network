import pytest

from genesis.budget import CycleBudget


def test_default_budget_valid():
    CycleBudget().validate()


def test_budget_accepts_allowed_integer_boundaries():
    CycleBudget(max_research_items=0, max_model_candidates=100, max_team_tasks=1).validate()


def test_budget_rejects_unbounded_values():
    with pytest.raises(ValueError, match="out of bounds"):
        CycleBudget(max_research_items=1000).validate()


@pytest.mark.parametrize("field", ("max_research_items", "max_model_candidates", "max_team_tasks"))
@pytest.mark.parametrize("value", (True, False))
def test_budget_rejects_boolean_values(field, value):
    values = {
        "max_research_items": 5,
        "max_model_candidates": 10,
        "max_team_tasks": 8,
    }
    values[field] = value
    with pytest.raises(ValueError, match="must be an integer"):
        CycleBudget(**values).validate()


@pytest.mark.parametrize("field", ("max_research_items", "max_model_candidates", "max_team_tasks"))
@pytest.mark.parametrize("value", (1.5, "5", None))
def test_budget_rejects_non_integer_values(field, value):
    values = {
        "max_research_items": 5,
        "max_model_candidates": 10,
        "max_team_tasks": 8,
    }
    values[field] = value
    with pytest.raises(ValueError, match="must be an integer"):
        CycleBudget(**values).validate()

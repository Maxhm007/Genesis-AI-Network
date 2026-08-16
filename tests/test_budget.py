import pytest
from genesis.budget import CycleBudget

def test_default_budget_valid():
    CycleBudget().validate()

def test_budget_rejects_unbounded_values():
    with pytest.raises(ValueError):
        CycleBudget(max_research_items=1000).validate()

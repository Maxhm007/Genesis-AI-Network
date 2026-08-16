import json

from genesis.providers import BootstrapProvider, ProviderRegistry
from genesis.team import AITeam


def test_bootstrap_provider_is_always_available_and_bounded():
    provider = BootstrapProvider()
    assert provider.available() is True
    payload = json.loads(provider.reason("ROLE: reviewer\nOBJECTIVE: test objective"))
    assert payload["provider_type"] == "deterministic-bootstrap"
    assert payload["role"] == "reviewer"
    assert "No new scientific fact" in payload["finding"]
    assert payload["smallest_next_action"]


def test_ai_team_operates_without_external_provider():
    registry = ProviderRegistry(include_bootstrap=True)
    team = AITeam(registry)
    outputs = team.run_task("Test Genesis autonomous team")
    assert len(outputs) == 8
    assert all(item["status"] == "completed" for item in outputs)
    assert all(item["provider"] == "genesis-bootstrap" for item in outputs)

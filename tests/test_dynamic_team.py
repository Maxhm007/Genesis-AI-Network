from genesis.providers import ProviderRegistry
from genesis.team import AITeam


def test_team_auto_adds_needed_specialists_without_duplicates():
    team = AITeam(ProviderRegistry(include_bootstrap=False))
    original = len(team.roles)

    output = team.run_task(
        "Evaluate aging, gene therapy, distributed replication, and cryptographic signatures",
        "Need longevity science and network resilience review",
    )

    roster = team.roster()
    capabilities = {item["capability"] for item in roster if item["dynamic"]}
    assert {"geroscience", "genomics", "distributed_systems", "cryptography"}.issubset(capabilities)
    assert len(team.roles) > original

    first_count = len(team.roles)
    team.run_task("Review aging and gene therapy again")
    assert len(team.roles) == first_count
    assert all(item["status"] == "waiting_for_provider" for item in output)


def test_dynamic_specialist_has_no_authority_escalation():
    team = AITeam(ProviderRegistry())
    role = team.add_specialist("cybersecurity")
    assert role.dynamic is True
    instruction = role.system_instruction.lower()
    assert "cannot modify the genesis constitution" in instruction
    assert "cannot" in instruction and "approve its own work" in instruction
    assert "grant itself new permissions" in instruction


def test_unknown_specialist_is_rejected():
    team = AITeam(ProviderRegistry())
    try:
        team.add_specialist("supreme_unbounded_controller")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown specialist must not be activated")


def test_dynamic_team_growth_is_bounded():
    team = AITeam(ProviderRegistry(), max_dynamic_roles=1)
    team.add_specialist("geroscience")
    try:
        team.add_specialist("genomics")
    except RuntimeError:
        pass
    else:
        raise AssertionError("dynamic-team resource bound must be enforced")

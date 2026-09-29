from scripts.genesis_teammate import should_route_owner_comment


def test_nexus_ignores_explicit_genesis_metadata_comments():
    assert not should_route_owner_comment("<!-- genesis-nexus-admin -->\nDeployment note")


def test_nexus_ignores_setup_status_note_without_action():
    text = """### Nexus is live

Use this issue as the **only owner-facing AI team chat**.

**Authority model:** Genesis = Brain → Nexus = Team Leader.
"""
    assert not should_route_owner_comment(text)


def test_nexus_routes_short_action_request():
    assert should_route_owner_comment("Check why Genesis is not closing issues automatically.")


def test_nexus_routes_status_prefix_when_it_contains_action():
    assert should_route_owner_comment("Status note: check the latest workflow failure")


def test_nexus_routes_implicit_plain_owner_message():
    assert should_route_owner_comment("Genesis is not automatic yet")


def test_nexus_recognizes_team_evolution_requests():
    from scripts.genesis_teammate import is_team_evolution_request
    assert is_team_evolution_request("Add a new security teammate")
    assert is_team_evolution_request("Modify agent Forge role")
    assert not is_team_evolution_request("Check issue #867")


def test_nexus_casual_messages_do_not_require_task_routing():
    from scripts.genesis_teammate import casual_response
    assert casual_response("Hi!") is not None
    assert casual_response("Thank you.") is not None


def test_engineering_handoff_chain():
    from scripts.genesis_teammate import next_handoff
    objective = "Investigate the failed workflow, fix it, and verify the repair"
    assert next_handoff("recovery", objective) == "forge"
    assert next_handoff("forge", objective) == "sentinel"
    assert next_handoff("sentinel", objective) is None


def test_non_engineering_request_does_not_force_handoff():
    from scripts.genesis_teammate import next_handoff
    assert next_handoff("atlas", "Plan a cleaner architecture") is None

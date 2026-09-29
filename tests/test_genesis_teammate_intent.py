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

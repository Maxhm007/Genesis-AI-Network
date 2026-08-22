from scripts.local_reasoning_provider import role_token_budget


def test_internal_code_reviewer_has_compact_generation_budget() -> None:
    prompt = "ROLE: genesis_internal_code_reviewer\nReturn JSON only.\n"
    assert role_token_budget(prompt) == 128


def test_bounded_coding_engineer_has_compact_generation_budget() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert role_token_budget(prompt) == 256


def test_other_roles_keep_their_configured_generation_budget() -> None:
    prompt = "ROLE: genesis_coding\nImplement the bounded change.\n"
    assert role_token_budget(prompt) is None

from scripts.local_reasoning_provider import json_completion_reserve_tokens, role_token_budget


def test_internal_code_reviewer_has_compact_generation_budget() -> None:
    prompt = "ROLE: genesis_internal_code_reviewer\nReturn JSON only.\n"
    assert role_token_budget(prompt) == 128


def test_bounded_coding_engineer_has_compact_initial_generation_budget() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert role_token_budget(prompt) == 256


def test_incomplete_coding_json_gets_only_remaining_configured_reserve() -> None:
    assert json_completion_reserve_tokens(
        '{"edits":[{"path":"genesis/coding.py","new":"unfinished',
        generated_tokens=256,
        requested_budget=256,
        configured_budget=384,
    ) == 128


def test_completion_reserve_does_not_extend_complete_early_or_non_json_output() -> None:
    assert json_completion_reserve_tokens(
        '{"edits":[]}',
        generated_tokens=256,
        requested_budget=256,
        configured_budget=384,
    ) == 0
    assert json_completion_reserve_tokens(
        '{"edits":[',
        generated_tokens=120,
        requested_budget=256,
        configured_budget=384,
    ) == 0
    assert json_completion_reserve_tokens(
        "not json",
        generated_tokens=256,
        requested_budget=256,
        configured_budget=384,
    ) == 0
    assert json_completion_reserve_tokens(
        '{"edits":[',
        generated_tokens=256,
        requested_budget=256,
        configured_budget=256,
    ) == 0


def test_other_roles_keep_their_configured_generation_budget() -> None:
    prompt = "ROLE: genesis_coding\nImplement the bounded change.\n"
    assert role_token_budget(prompt) is None

from scripts.local_reasoning_provider import (
    json_completion_reserve_tokens,
    role_completion_budget,
    role_token_budget,
)


def test_internal_code_reviewer_has_compact_generation_budget() -> None:
    prompt = "ROLE: genesis_internal_code_reviewer\nReturn JSON only.\n"
    assert role_token_budget(prompt) == 128


def test_bounded_coding_engineer_has_compact_initial_generation_budget() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert role_token_budget(prompt) == 128


def test_bounded_coding_engineer_has_hard_total_generation_budget() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert role_completion_budget(prompt) == 160


def test_incomplete_coding_json_gets_only_small_completion_reserve() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert json_completion_reserve_tokens(
        '{"edits":[{"path":"genesis/coding.py","new":"unfinished',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=role_completion_budget(prompt) or 128,
    ) == 32


def test_completion_reserve_does_not_extend_complete_early_or_non_json_output() -> None:
    assert json_completion_reserve_tokens(
        '{"edits":[]}',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=160,
    ) == 0
    assert json_completion_reserve_tokens(
        '{"edits":[',
        generated_tokens=120,
        requested_budget=128,
        configured_budget=160,
    ) == 0
    assert json_completion_reserve_tokens(
        "not json",
        generated_tokens=128,
        requested_budget=128,
        configured_budget=160,
    ) == 0
    assert json_completion_reserve_tokens(
        '{"edits":[',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=128,
    ) == 0


def test_other_roles_keep_their_configured_generation_budget() -> None:
    prompt = "ROLE: genesis_coding\nImplement the bounded change.\n"
    assert role_token_budget(prompt) is None
    assert role_completion_budget(prompt) is None

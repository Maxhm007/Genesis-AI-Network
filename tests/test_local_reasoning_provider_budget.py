from scripts.local_reasoning_provider import (
    json_completion_reserve_tokens,
    role_completion_budget,
    role_token_budget,
    simplify_bounded_coding_prompt,
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


def test_bounded_coding_prompt_unwraps_initial_schema_example() -> None:
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        'OUTPUT: JSON only in this shape: {"edits":[{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"replacement text"}]}\n'
        "OBJECTIVE: keep this evidence unchanged\n"
    )
    simplified = simplify_bounded_coding_prompt(prompt)
    assert "JSON only as ONE flat edit object" in simplified
    assert '"path":"genesis/example.py"' in simplified
    assert '"edits"' not in simplified
    assert "OBJECTIVE: keep this evidence unchanged" in simplified


def test_bounded_coding_prompt_unwraps_retry_schema_but_preserves_previous_output() -> None:
    previous = '{"edits":[{"path":"genesis/previous.py","new":"keep diagnostic wrapper"}]}'
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        f"PREVIOUS: {previous}\n"
        'Return ONLY the same JSON shape as: {"edits":[{"path":"genesis/example.py","start_line":7,"end_line":7,"new":"replacement text"}]}. Verify it.\n'
    )
    simplified = simplify_bounded_coding_prompt(prompt)
    assert f"PREVIOUS: {previous}" in simplified
    assert "Return ONLY ONE flat edit object like:" in simplified
    assert 'like: {"path":"genesis/example.py","start_line":7,"end_line":7,"new":"replacement text"}' in simplified


def test_prompt_simplification_does_not_change_other_roles() -> None:
    prompt = (
        "ROLE: genesis_internal_code_reviewer\n"
        'OUTPUT: JSON only in this shape: {"edits":[{"path":"genesis/example.py","new":"x"}]}\n'
    )
    assert simplify_bounded_coding_prompt(prompt) == prompt


def test_incomplete_coding_json_gets_only_small_completion_reserve() -> None:
    prompt = "ROLE: bounded_coding_engineer\nReturn one compact edit as JSON.\n"
    assert json_completion_reserve_tokens(
        '{"path":"genesis/coding.py","new":"unfinished',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=role_completion_budget(prompt) or 128,
    ) == 32


def test_completion_reserve_does_not_extend_complete_early_or_non_json_output() -> None:
    assert json_completion_reserve_tokens(
        '{"path":"genesis/example.py","new":"x"}',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=160,
    ) == 0
    assert json_completion_reserve_tokens(
        '{"path":"genesis/example.py",',
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
        '{"path":"genesis/example.py",',
        generated_tokens=128,
        requested_budget=128,
        configured_budget=128,
    ) == 0


def test_other_roles_keep_their_configured_generation_budget() -> None:
    prompt = "ROLE: genesis_coding\nImplement the bounded change.\n"
    assert role_token_budget(prompt) is None
    assert role_completion_budget(prompt) is None

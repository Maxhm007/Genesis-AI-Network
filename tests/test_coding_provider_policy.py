from __future__ import annotations

from genesis.coding import CodingModule
from genesis.coding_provider_policy import (
    CODING_ROLE,
    MAX_BOUNDED_EDITS,
    TRANSPORT_CODING_ROLE,
    _transport_prompt,
)
from genesis.providers import _reasoning_token_budget
from scripts.local_reasoning_provider import role_token_budget


def test_coding_transport_role_uses_configured_provider_budget() -> None:
    prompt = (
        f"ROLE: {CODING_ROLE}\n"
        "TASK: Make exactly ONE smallest useful edit toward OBJECTIVE using only NUMBERED_CONTEXT.\n"
        "RULES: exactly one edit; Exactly one edit. Return only the required one-edit JSON.\n"
    )

    transported = _transport_prompt(prompt)

    assert transported.startswith(f"ROLE: {TRANSPORT_CODING_ROLE}\n")
    assert "EDIT_BUDGET:" in transported
    assert "one or two smallest useful edits" in transported
    assert "one or two tightly related edits" in transported
    assert _reasoning_token_budget(transported) is None
    assert role_token_budget(transported) is None


def test_non_coding_prompt_is_not_rewritten() -> None:
    prompt = "ROLE: planner\nReturn a bounded plan.\n"
    assert _transport_prompt(prompt) == prompt


def test_policy_keeps_edit_scope_bounded_to_two() -> None:
    assert MAX_BOUNDED_EDITS == 2
    assert CodingModule.MAX_EDITS == 2

from __future__ import annotations

from pathlib import Path

from genesis.coding import CodingModule
from genesis.coding_provider_policy import (
    CODING_ROLE,
    MAX_BOUNDED_EDITS,
    TRANSPORT_CODING_ROLE,
    _transport_prompt,
)
from genesis.providers import GenesisHTTPProvider, ProviderRegistry, _reasoning_token_budget
from scripts.local_reasoning_provider import role_token_budget


class TwoEditHTTPProvider(GenesisHTTPProvider):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:1", name="bounded-http-test")

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return (
            '{"edits":['
            '{"path":"genesis/example.py","old":"A = 1","new":"A = 2"},'
            '{"path":"genesis/example.py","old":"B = 2","new":"B = 3"}'
            ']}'
        )


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


def test_http_repair_lane_allows_two_related_edits_without_widening_default(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("A = 1\nB = 2\n", encoding="utf-8")
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))

    proposal = module.propose(
        "Update the paired bounded values.",
        ["genesis/example.py"],
        provider=TwoEditHTTPProvider(),
    )

    assert proposal.files["genesis/example.py"] == "A = 2\nB = 3\n"
    assert MAX_BOUNDED_EDITS == 2
    assert CodingModule.MAX_EDITS == 1
    assert "MAX_EDITS" not in module.__dict__

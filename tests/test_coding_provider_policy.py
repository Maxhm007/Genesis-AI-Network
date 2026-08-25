from __future__ import annotations

from pathlib import Path

from genesis.coding import CodingModule
from genesis.coding_provider_policy import (
    CODING_ROLE,
    MAX_BOUNDED_EDITS,
    TRANSPORT_CODING_ROLE,
    _ground_issue_context_paths,
    _request_focus_text,
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


def _write(tmp_path: Path, relative: str, text: str) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


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


def test_request_focus_excludes_prior_validation_memory() -> None:
    focus = _request_focus_text(
        "TITLE: Autorepair can promote semantic no-op fixes\n"
        "BODY:\n"
        "A previous failure changed `genesis/budget.py`.\n\n"
        "Required system improvement:\n"
        "- require semantic issue satisfaction before promotion.\n\n"
        "PRIOR_VALIDATION_EVIDENCE:\n"
        "Rejected attempt repeatedly edited `genesis/budget.py`.\n"
    )

    assert "semantic issue satisfaction" in focus
    assert "PRIOR_VALIDATION_EVIDENCE" not in focus
    assert "genesis/budget.py" not in focus


def test_historical_file_mention_does_not_override_requested_system_improvement(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/budget.py", "class CycleBudget:\n    pass\n")
    _write(
        tmp_path,
        "genesis/semantic_validation.py",
        "def verify_issue_satisfaction(candidate, acceptance, evidence):\n"
        "    # reject semantic no-op candidate changes without acceptance evidence\n"
        "    return candidate and acceptance and evidence\n",
    )
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    context = ["genesis/budget.py"]
    objective = (
        "Resolve exactly the described software defect.\n"
        "ISSUE_EVIDENCE:\n"
        "TITLE: Autorepair can promote semantic no-op fixes\n"
        "BODY:\n"
        "A previous failure changed `genesis/budget.py` but did not solve the reported defect.\n\n"
        "Required system improvement:\n"
        "- require semantic issue satisfaction and issue-specific acceptance evidence;\n"
        "- reject no-op candidates before promotion.\n\n"
        "PRIOR_VALIDATION_EVIDENCE:\n"
        "Earlier rejected attempts repeatedly edited `genesis/budget.py`.\n"
        "Rejected target: `genesis/budget.py`.\n"
    )

    grounded = _ground_issue_context_paths(module, objective, context)

    assert grounded[0] == "genesis/semantic_validation.py"
    assert context[0] == "genesis/semantic_validation.py"


def test_explicit_path_in_requested_fix_remains_highest_priority(tmp_path: Path) -> None:
    _write(tmp_path, "genesis/alpha.py", "def repair_alpha():\n    return False\n")
    _write(
        tmp_path,
        "genesis/semantic_validation.py",
        "def verify_issue_satisfaction(candidate, acceptance):\n    return candidate and acceptance\n",
    )
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    context = ["genesis/semantic_validation.py"]
    objective = (
        "ISSUE_EVIDENCE:\n"
        "TITLE: Alpha repair is wrong\n"
        "BODY:\n"
        "Historical diagnostics mention semantic validation.\n\n"
        "Required fix:\n"
        "Update `genesis/alpha.py` so the alpha repair returns the correct result.\n"
    )

    grounded = _ground_issue_context_paths(module, objective, context)

    assert grounded[0] == "genesis/alpha.py"
    assert context[0] == "genesis/alpha.py"

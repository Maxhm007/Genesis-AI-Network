"""Regression coverage for the staged Agentic Lab test-first proposal gate."""

from pathlib import Path

from genesis.coding import CodingModule, CodingProposal
from scripts.github_issue_autorepair import (
    allowed_issue_repair_paths,
    propose_issue_repair,
    solve_reported_issue,
)


def _fixture(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text(
        "def clamp(value):\n    return value\n", encoding="utf-8"
    )
    return {"number": 17, "title": "Clamp", "body": "Fix `genesis/alpha.py` so clamp(50) == 10"}


class _CodeOnlyProvider:
    name = "code-only"

    def reason(self, prompt):
        return '{"edits":[{"path":"genesis/alpha.py","start_line":2,"end_line":2,"new":"    return min(value, 10)"}]}'


class _PairedProvider:
    name = "paired"

    def reason(self, prompt):
        return (
            '{"edits":['
            '{"path":"genesis/alpha.py","start_line":2,"end_line":2,"new":"    return min(value, 10)"},'
            '{"path":"tests/test_alpha.py","insert_after_line":0,'
            '"new":"from genesis.alpha import clamp\\n\\ndef test_clamp_caps_large_values():\\n    assert clamp(50) == 10\\n"}'
            ']}'
        )


def test_code_only_proposal_rejected_in_test_first_mode(tmp_path):
    issue = _fixture(tmp_path)
    try:
        propose_issue_repair(
            issue, ["genesis/alpha.py"], tmp_path,
            provider=_CodeOnlyProvider(), require_regression_test=True,
        )
    except ValueError as exc:
        assert "test-first" in str(exc)
    else:
        raise AssertionError("code-only proposal bypassed test-first gate")


def test_paired_proposal_has_one_fix_and_one_regression_test(tmp_path):
    issue = _fixture(tmp_path)
    proposal = propose_issue_repair(
        issue, ["genesis/alpha.py"], tmp_path,
        provider=_PairedProvider(), require_regression_test=True,
    )
    assert set(proposal.files) == {"genesis/alpha.py", "tests/test_alpha.py"}
    assert "clamp(50) == 10" in proposal.files["tests/test_alpha.py"]


def test_agentic_env_gate_fails_closed_without_test(monkeypatch, tmp_path):
    issue = _fixture(tmp_path)
    monkeypatch.setenv("GENESIS_REQUIRE_REGRESSION_TEST", "1")

    class NeverExecute:
        def execute(self, proposal):
            raise AssertionError("invalid proposal must never reach execution")

    result = solve_reported_issue(
        issue, tmp_path, provider=_CodeOnlyProvider(), executor=NeverExecute()
    )
    assert result.status == "retry_pending_capability"
    assert result.proposal is None


def test_script_target_supports_conventional_regression_test():
    assert "tests/test_example.py" in allowed_issue_repair_paths(
        ["scripts/example.py"]
    )

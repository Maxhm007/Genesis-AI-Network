"""Regression coverage for the staged Agentic Lab test-first proposal gate."""

from pathlib import Path
from types import SimpleNamespace

import scripts.github_issue_autorepair as autorepair

from scripts.agentic_strategy_repair import _micro_repair_or_original
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
    assert "tests/test_example_regression.py" in allowed_issue_repair_paths(
        ["scripts/example.py"]
    )
    assert "tests/test_other_regression.py" not in allowed_issue_repair_paths(
        ["scripts/example.py"]
    )


def test_agentic_micro_repair_cannot_bypass_test_first(monkeypatch, tmp_path):
    calls = []

    def original(issue, paths, root, **kwargs):
        calls.append(kwargs)
        return "strict-proposal"

    outcome = _micro_repair_or_original(
        original, {"title": "navigation landmark aria-label"},
        ["scripts/render_static_dashboard.py"], tmp_path,
        require_regression_test=True,
    )
    assert outcome == "strict-proposal"
    assert calls == [{"require_regression_test": True}]


def test_test_first_mode_rejects_non_red_regression_before_executor(monkeypatch, tmp_path):
    issue = _fixture(tmp_path)
    monkeypatch.setenv("GENESIS_REQUIRE_REGRESSION_TEST", "1")
    monkeypatch.setattr(
        autorepair, "verify_regression_fails_on_baseline",
        lambda root, files: (False, "test unexpectedly passed on baseline"),
    )

    class NeverExecute:
        def execute(self, proposal):
            raise AssertionError("non-red regression must not execute a fix")

    result = solve_reported_issue(
        issue, tmp_path, provider=_PairedProvider(), executor=NeverExecute()
    )
    assert result.status == "repair_rejected_regression_not_red"
    assert result.provider_failure["outcome"] == "regression_not_red"


def test_red_phase_only_checks_an_added_test_function(tmp_path):
    issue = _fixture(tmp_path)
    # The code-only path is rejected before any Git worktree is created.
    passed, reason = autorepair.verify_regression_fails_on_baseline(
        tmp_path, {"genesis/alpha.py": "VALUE = 2\\n"}
    )
    assert not passed and "one regression test" in reason


def test_red_phase_does_not_inherit_github_credentials(monkeypatch, tmp_path):
    _fixture(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "not-a-real-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-secret")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--unexpected-option")
    seen = []

    def fake_run(command, **kwargs):
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if len(command) >= 3 and command[1:3] == ["-m", "pytest"]:
            env = kwargs["env"]
            seen.append(env)
            return SimpleNamespace(
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_clamp_caps_large_values\nE assert 50 == 10\n1 failed\n",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    passed, message = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\ndef test_clamp_caps_large_values():\n"
            "    assert clamp(50) == 10\n"
        )},
    )
    assert passed, message
    assert len(seen) == 1
    assert "GH_TOKEN" not in seen[0] and "GITHUB_TOKEN" not in seen[0]
    assert "PYTEST_ADDOPTS" not in seen[0]
    assert seen[0]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_red_phase_rejects_runtime_errors_even_with_failed_node(monkeypatch, tmp_path):
    _fixture(tmp_path)

    def fake_run(command, **kwargs):
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if len(command) >= 3 and command[1:3] == ["-m", "pytest"]:
            return SimpleNamespace(
                returncode=1,
                stdout=(
                    "FAILED tests/test_alpha.py::test_clamp_caps_large_values - RuntimeError\n"
                    "E RuntimeError: broken environment\n1 failed\n"
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    ok, detail = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
        )},
    )
    assert not ok
    assert "not an assertion" in detail

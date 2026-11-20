"""Regression coverage for the staged Agentic Lab test-first proposal gate."""

from pathlib import Path
import subprocess
import shutil

import pytest
from types import SimpleNamespace

import scripts.github_issue_autorepair as autorepair

from scripts.agentic_strategy_repair import _micro_repair_or_original
from scripts.github_issue_autorepair import (
    allowed_issue_repair_paths,
    propose_issue_repair,
    solve_reported_issue,
)



def _fake_docker_result(kwargs, *, returncode, stdout, stderr):
    kwargs["stdout"].write(stdout)
    kwargs["stderr"].write(stderr)
    return SimpleNamespace(returncode=returncode)

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
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "run"]:
            env = kwargs["env"]
            assert "--network" in command and command[command.index("--network") + 1] == "none"
            assert "--read-only" in command and "--cap-drop" in command
            assert "--mount" in command
            assert command[command.index("--mount") + 1].endswith(",target=/workspace,readonly")
            assert "/var/run/docker.sock" not in " ".join(command)
            seen.append(env)
            return _fake_docker_result(kwargs,
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_clamp_caps_large_values\nE assert 50 == 10\n1 failed\n",
                stderr="GENESIS_RED_PHASE_VERDICT:{\"category\": \"assertion\", \"nodeid\": \"tests/test_alpha.py::test_clamp_caps_large_values\", \"phase\": \"call\"}\n",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    passed, message = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\ndef test_clamp_caps_large_values():\n"
            "    assert clamp(50) == 10\n"
        )},
    )
    assert passed, message
    assert len(seen) == 1
    assert "GH_TOKEN" not in seen[0] and "GITHUB_TOKEN" not in seen[0]
    assert "PYTEST_ADDOPTS" not in seen[0]
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in seen[0]


def test_red_phase_rejects_runtime_errors_even_with_failed_node(monkeypatch, tmp_path):
    _fixture(tmp_path)

    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "run"]:
            return _fake_docker_result(kwargs,
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
        {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
        )},
    )
    assert not ok
    assert "classified assertion" in detail


def test_real_pytest_rewritten_assertion_is_accepted_as_red_phase(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker sandbox unavailable in local development")
    if subprocess.run(
        ["docker", "image", "inspect", "genesis-red-phase:local"],
        capture_output=True, check=False,
    ).returncode != 0:
        pytest.skip("Trusted red-phase image not built")
    _fixture(tmp_path)
    for args in (
        ("init", "-q"),
        ("config", "user.name", "Genesis Test"),
        ("config", "user.email", "genesis-test@example.invalid"),
        ("add", "genesis/alpha.py"),
        ("commit", "-qm", "baseline"),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    ok, reason = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
        )},
    )
    assert ok, reason


def test_red_phase_fails_closed_without_trusted_container(monkeypatch, tmp_path):
    _fixture(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        raise AssertionError("host must not execute generated pytest code")

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    ok, reason = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
        )},
    )
    assert not ok and "image unavailable" in reason
    assert len(calls) == 1


def test_sandbox_never_passes_host_token_into_docker(monkeypatch, tmp_path):
    _fixture(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "secret-not-for-container")
    monkeypatch.setenv("GITHUB_TOKEN", "another-secret")
    seen = []

    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "run"]:
            seen.append((command, kwargs["env"]))
            return _fake_docker_result(kwargs,
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_clamp_caps_large_values\nE assert 50 == 10\n1 failed\n",
                stderr="GENESIS_RED_PHASE_VERDICT:{\"category\": \"assertion\", \"nodeid\": \"tests/test_alpha.py::test_clamp_caps_large_values\", \"phase\": \"call\"}\n",
            )
        raise AssertionError(command)

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    ok, message = autorepair.verify_regression_fails_on_baseline(
        tmp_path,
        {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n    assert clamp(50) == 10\n"
        )},
    )
    assert ok, message
    assert len(seen) == 1
    assert not any("secret-not-for-container" in value for value in map(str, seen[0]))
    assert "GH_TOKEN" not in seen[0][1] and "GITHUB_TOKEN" not in seen[0][1]
    assert "--network" in seen[0][0] and "none" in seen[0][0]


def test_runtime_error_cannot_spoof_assertion_marker(monkeypatch, tmp_path):
    _fixture(tmp_path)

    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "add"]:
            return SimpleNamespace(returncode=0)
        if command[:3] == ["git", "worktree", "remove"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "run"]:
            return _fake_docker_result(kwargs,
                returncode=1,
                stdout="FAILED tests/test_alpha.py::test_clamp_caps_large_values - RuntimeError\n"
                       "E RuntimeError: backend unavailable\n"
                       "assert clamp(50) == 10, 'AssertionError: expected clamp'\n1 failed\n",
                stderr='GENESIS_RED_PHASE_VERDICT:{"category": "other", '
                       '"nodeid": "tests/test_alpha.py::test_clamp_caps_large_values", '
                       '"phase": "call"}\n',
            )
        raise AssertionError(command)

    monkeypatch.setattr(autorepair.subprocess, "run", fake_run)
    ok, detail = autorepair.verify_regression_fails_on_baseline(
        tmp_path, {"genesis/alpha.py": "def clamp(value):\n    return min(value, 10)\n", "tests/test_alpha.py": (
            "from genesis.alpha import clamp\n\n"
            "def test_clamp_caps_large_values():\n"
            "    assert clamp(50) == 10\n"
        )},
    )
    assert not ok and "classified assertion" in detail

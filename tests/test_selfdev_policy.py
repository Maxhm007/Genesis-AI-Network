from pathlib import Path

import pytest

from genesis.selfdev import SelfDevelopmentExecutor, normalize_selfdev_path


def test_selfdev_rejects_constitution_change(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    with pytest.raises(RuntimeError):
        executor._validate_paths(["GENESIS_CONSTITUTION.md"])


def test_selfdev_rejects_workflow_permission_change(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    with pytest.raises(RuntimeError):
        executor._validate_paths([".github/workflows/selfdev.yml"])


def test_selfdev_rejects_parent_traversal_even_with_allowed_prefix(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    with pytest.raises(RuntimeError, match="traversal"):
        executor._validate_paths(["genesis/../.git/config"])
    with pytest.raises(RuntimeError, match="traversal"):
        executor._validate_paths(["genesis/../GENESIS_CONSTITUTION.md"])
    with pytest.raises(RuntimeError, match="traversal"):
        executor._validate_paths(["genesis/../../outside.txt"])


def test_selfdev_rejects_absolute_path(tmp_path: Path):
    with pytest.raises(RuntimeError):
        normalize_selfdev_path(tmp_path, "/tmp/genesis/evil.py")


def test_selfdev_rejects_symlink_escape(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir(exist_ok=True)
    link = tmp_path / "genesis" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(RuntimeError, match="outside repository"):
        normalize_selfdev_path(tmp_path, "genesis/escape/evil.py")


def test_selfdev_allows_bounded_code_and_tests(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    executor._validate_paths([
        "genesis/example.py",
        "tests/test_example.py",
        "docs/NOTE.md",
        "config/example.json",
    ])


def test_candidate_tests_do_not_inherit_live_provider_endpoints(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GENESIS_PROVIDER_URL", "http://127.0.0.1:8766")
    monkeypatch.setenv("GENESIS_PROVIDER_NAME", "qwen2.5-coder-1.5b-gene-pulse")
    monkeypatch.setenv("GENESIS_PROVIDER_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("GENESIS_PROVIDER_MAX_NEW_TOKENS", "384")
    monkeypatch.setenv("GENESIS_PROVIDER_ENDPOINTS", '[{"url":"http://127.0.0.1:9999"}]')
    monkeypatch.setenv("UNRELATED_TEST_SETTING", "kept")

    env = SelfDevelopmentExecutor(tmp_path)._candidate_test_env()

    assert "GENESIS_PROVIDER_URL" not in env
    assert "GENESIS_PROVIDER_NAME" not in env
    assert "GENESIS_PROVIDER_TIMEOUT_SECONDS" not in env
    assert "GENESIS_PROVIDER_MAX_NEW_TOKENS" not in env
    assert "GENESIS_PROVIDER_ENDPOINTS" not in env
    assert env["UNRELATED_TEST_SETTING"] == "kept"
    assert env["PYTHONPATH"] == str(tmp_path.resolve())

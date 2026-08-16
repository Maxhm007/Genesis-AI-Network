from pathlib import Path

import pytest

from genesis.selfdev import SelfDevelopmentExecutor


def test_selfdev_rejects_constitution_change(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    with pytest.raises(RuntimeError):
        executor._validate_paths(["GENESIS_CONSTITUTION.md"])


def test_selfdev_rejects_workflow_permission_change(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    with pytest.raises(RuntimeError):
        executor._validate_paths([".github/workflows/selfdev.yml"])


def test_selfdev_allows_bounded_code_and_tests(tmp_path: Path):
    executor = SelfDevelopmentExecutor(tmp_path)
    executor._validate_paths([
        "genesis/example.py",
        "tests/test_example.py",
        "docs/NOTE.md",
        "config/example.json",
    ])

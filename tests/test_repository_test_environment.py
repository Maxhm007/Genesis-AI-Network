from __future__ import annotations

import importlib.util
import os
from pathlib import Path


PROVIDER_ENV = (
    "GENESIS_PROVIDER_URL",
    "GENESIS_PROVIDER_NAME",
    "GENESIS_PROVIDER_TIMEOUT_SECONDS",
    "GENESIS_PROVIDER_MAX_NEW_TOKENS",
    "GENESIS_PROVIDER_ENDPOINTS",
)


def test_repository_conftest_strips_inherited_live_provider_environment(monkeypatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.setenv(name, "inherited-live-provider")

    path = Path(__file__).with_name("conftest.py")
    spec = importlib.util.spec_from_file_location("genesis_test_env_conftest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert all(name not in os.environ for name in PROVIDER_ENV)

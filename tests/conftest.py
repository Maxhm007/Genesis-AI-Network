from __future__ import annotations

import os


INHERITED_PROVIDER_ENV = (
    "GENESIS_PROVIDER_URL",
    "GENESIS_PROVIDER_NAME",
    "GENESIS_PROVIDER_TIMEOUT_SECONDS",
    "GENESIS_PROVIDER_MAX_NEW_TOKENS",
    "GENESIS_PROVIDER_ENDPOINTS",
)


def sanitize_inherited_provider_environment() -> None:
    """Keep repository tests hermetic from live Gene Pulse provider endpoints.

    Workflows may configure a reasoning provider for Genesis runtime tasks. The
    repository test suite must not inherit that live endpoint implicitly because
    tests that construct default provider registries can otherwise perform model
    or network calls and stall internal review. Tests that exercise provider
    integration can still configure their own environment explicitly after
    collection starts.
    """
    for name in INHERITED_PROVIDER_ENV:
        os.environ.pop(name, None)


sanitize_inherited_provider_environment()

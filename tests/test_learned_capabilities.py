from __future__ import annotations

import pytest

from genesis.learned_capabilities import (
    list_capabilities,
    register_capability,
    run_capability,
    validate_registry,
)


def test_learned_capability_registry_executes_registered_handler() -> None:
    name = "test_echo_capability"
    existing = {capability.name for capability in list_capabilities()}
    if name not in existing:
        register_capability(
            name,
            "Return one bounded value for registry contract testing.",
            "test evidence",
            lambda value: value,
        )

    assert run_capability(name, "ok") == "ok"
    assert validate_registry() is True


def test_learned_capability_registry_rejects_unknown_capability() -> None:
    with pytest.raises(KeyError):
        run_capability("definitely_missing_capability")

from __future__ import annotations

import pytest

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry


class LiveCodingProvider:
    name = "qwen3-0.6b-local"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return '{"title":"noop","rationale":"test","files":{"docs/provider-handoff.txt":"ok\\n"}}'


class UnavailableCodingProvider(LiveCodingProvider):
    def available(self) -> bool:
        return False


def _force_router_rejection(module: CodingModule, monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args, **kwargs):
        raise RuntimeError("telemetry threshold rejected provider")

    monkeypatch.setattr(module.router, "select", reject)


def test_coding_falls_back_to_live_non_bootstrap_provider_when_telemetry_rejects(tmp_path, monkeypatch):
    registry = ProviderRegistry(include_bootstrap=True)
    provider = LiveCodingProvider()
    registry.register(provider)
    module = CodingModule(tmp_path, registry)
    _force_router_rejection(module, monkeypatch)

    selected = module._provider()

    assert selected is provider
    assert selected.name == "qwen3-0.6b-local"


def test_coding_fallback_never_uses_bootstrap_as_code_generator(tmp_path, monkeypatch):
    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(UnavailableCodingProvider())
    module = CodingModule(tmp_path, registry)
    _force_router_rejection(module, monkeypatch)

    assert module._provider() is None

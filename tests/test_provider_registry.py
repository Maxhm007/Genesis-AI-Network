from __future__ import annotations

import json

from genesis.providers import GenesisHTTPProvider, MAX_PROVIDER_TIMEOUT_SECONDS, ProviderRegistry


def _http_providers(registry: ProviderRegistry) -> list[GenesisHTTPProvider]:
    return [provider for provider in registry._providers if isinstance(provider, GenesisHTTPProvider)]


def test_registry_supports_multiple_replaceable_http_providers(monkeypatch):
    monkeypatch.delenv("GENESIS_PROVIDER_URL", raising=False)
    monkeypatch.setenv(
        "GENESIS_PROVIDER_ENDPOINTS",
        json.dumps(
            [
                {"name": "local-coder", "url": "http://127.0.0.1:8766", "timeout_seconds": 30},
                {"name": "research-model", "url": "http://127.0.0.1:8767", "timeout_seconds": 45},
                {"name": "genesis-specialist", "url": "http://127.0.0.1:8768", "timeout_seconds": 90},
            ]
        ),
    )

    providers = _http_providers(ProviderRegistry(include_bootstrap=False))

    assert [provider.name for provider in providers] == ["local-coder", "research-model", "genesis-specialist"]
    assert [provider.base_url for provider in providers] == [
        "http://127.0.0.1:8766",
        "http://127.0.0.1:8767",
        "http://127.0.0.1:8768",
    ]
    assert [provider.timeout for provider in providers] == [30.0, 45.0, 90.0]


def test_registry_preserves_legacy_single_provider_configuration(monkeypatch):
    monkeypatch.delenv("GENESIS_PROVIDER_ENDPOINTS", raising=False)
    monkeypatch.setenv("GENESIS_PROVIDER_URL", "http://legacy:9999/")
    monkeypatch.setenv("GENESIS_PROVIDER_NAME", "legacy-provider")
    monkeypatch.setenv("GENESIS_PROVIDER_TIMEOUT_SECONDS", "20")

    providers = _http_providers(ProviderRegistry(include_bootstrap=False))

    assert len(providers) == 1
    assert providers[0].name == "legacy-provider"
    assert providers[0].base_url == "http://legacy:9999"
    assert providers[0].timeout == 20.0


def test_registry_ignores_malformed_multi_provider_config_and_keeps_legacy(monkeypatch):
    monkeypatch.setenv("GENESIS_PROVIDER_ENDPOINTS", "not-json")
    monkeypatch.setenv("GENESIS_PROVIDER_URL", "http://legacy:9999")
    monkeypatch.setenv("GENESIS_PROVIDER_NAME", "legacy-provider")

    providers = _http_providers(ProviderRegistry(include_bootstrap=False))

    assert [(provider.name, provider.base_url) for provider in providers] == [
        ("legacy-provider", "http://legacy:9999")
    ]


def test_registry_deduplicates_exact_name_url_pair_and_bounds_timeout(monkeypatch):
    monkeypatch.setenv(
        "GENESIS_PROVIDER_ENDPOINTS",
        json.dumps(
            [
                {"name": "same", "url": "http://model:8000/", "timeout_seconds": 9999},
                {"name": "same", "url": "http://model:8000", "timeout_seconds": 10},
                {"name": "tiny-timeout", "url": "http://model:8001", "timeout_seconds": 1},
            ]
        ),
    )
    monkeypatch.delenv("GENESIS_PROVIDER_URL", raising=False)

    providers = _http_providers(ProviderRegistry(include_bootstrap=False))

    assert [(provider.name, provider.timeout) for provider in providers] == [
        ("same", MAX_PROVIDER_TIMEOUT_SECONDS),
        ("tiny-timeout", 5.0),
    ]

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class IntelligenceProvider(Protocol):
    name: str

    def available(self) -> bool:
        """Return True only when the provider can be used now."""
        ...

    def reason(self, prompt: str) -> str:
        """Return a model-generated response for a prompt."""
        ...


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    available: bool


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: list[IntelligenceProvider] = []

    def register(self, provider: IntelligenceProvider) -> None:
        self._providers.append(provider)

    def statuses(self) -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []
        for provider in self._providers:
            try:
                is_available = bool(provider.available())
            except Exception:
                is_available = False
            statuses.append(ProviderStatus(provider.name, is_available))
        return statuses

    def available_providers(self) -> list[IntelligenceProvider]:
        available: list[IntelligenceProvider] = []
        for provider in self._providers:
            try:
                if provider.available():
                    available.append(provider)
            except Exception:
                continue
        return available

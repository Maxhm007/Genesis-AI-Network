from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class IntelligenceProvider(Protocol):
    name: str

    def available(self) -> bool:
        """Return True only when the provider can be used now."""
        ...

    def reason(self, prompt: str) -> str:
        """Return a provider-generated response for a prompt."""
        ...


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    available: bool


class BootstrapProvider:
    """Dependency-free, deterministic bootstrap reasoning.

    This is intentionally modest. It gives Genesis a native planning/review
    capability when no model service exists, but it must not be represented as
    equivalent to a trained language model or as a source of scientific facts.
    It only transforms supplied context into bounded next actions.
    """

    name = "genesis-bootstrap"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        role = "general"
        objective = ""
        for line in prompt.splitlines():
            if line.startswith("ROLE:"):
                role = line.split(":", 1)[1].strip()
            elif line.startswith("OBJECTIVE:"):
                objective = line.split(":", 1)[1].strip()

        actions = {
            "planner": "Define one measurable milestone, its prerequisite evidence, and a reversible implementation step.",
            "researcher": "Identify the primary-source evidence needed next; do not convert metadata or hypotheses into established facts.",
            "model_scout": "Keep new models quarantined until license, provenance, capability, resource and security checks are complete.",
            "engineer": "Create an isolated candidate change with tests; do not overwrite stable code automatically.",
            "scientist": "Turn the objective into a falsifiable hypothesis and specify what evidence could disconfirm it.",
            "reviewer": "Look for unsupported claims, missing provenance, unsafe assumptions and hidden single points of failure.",
            "validator": "Require independent tests and explicit pass/fail criteria before any promotion decision.",
            "network_steward": "Add redundancy through compatible peers while preserving node-operator control and constitution verification.",
        }
        next_action = actions.get(role, "Choose the smallest reversible, testable next action.")
        return json.dumps(
            {
                "provider_type": "deterministic-bootstrap",
                "role": role,
                "objective": objective,
                "finding": "No new scientific fact is asserted by the bootstrap provider.",
                "evidence_gaps": ["Independent primary evidence or a stronger intelligence provider is required for factual conclusions."],
                "risks": ["Bootstrap reasoning is rule-based and limited; do not treat it as expert scientific judgement."],
                "smallest_next_action": next_action,
            },
            sort_keys=True,
        )


class GenesisHTTPProvider:
    """Optional provider implementing the tiny Genesis Provider Protocol.

    POST {base_url}/reason with JSON {"prompt": "..."}.
    Expected response: {"response": "..."}.
    This makes local, remote, distributed or future models pluggable without a
    dependency on a named vendor/runtime.
    """

    def __init__(self, base_url: str, name: str = "genesis-http", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.name = name
        self.timeout = timeout

    def available(self) -> bool:
        try:
            req = urllib.request.Request(
                self.base_url + "/health",
                headers={"User-Agent": "Genesis-AI-Network/0.1"},
            )
            with urllib.request.urlopen(req, timeout=min(self.timeout, 3.0)) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    def reason(self, prompt: str) -> str:
        body = json.dumps({"prompt": prompt}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/reason",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Genesis-AI-Network/0.1"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        value = payload.get("response")
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Provider returned no response text")
        return value


class ProviderRegistry:
    def __init__(self, include_bootstrap: bool = True) -> None:
        self._providers: list[IntelligenceProvider] = []
        if include_bootstrap:
            self.register(BootstrapProvider())
        provider_url = os.environ.get("GENESIS_PROVIDER_URL", "").strip()
        if provider_url:
            self.register(GenesisHTTPProvider(provider_url, os.environ.get("GENESIS_PROVIDER_NAME", "genesis-http")))

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

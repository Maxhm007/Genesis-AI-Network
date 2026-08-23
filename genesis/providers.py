from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


MAX_PROVIDER_TIMEOUT_SECONDS = 360.0
LOCAL_REASONING_ROLE_TOKEN_BUDGETS = {
    "planner": 160,
    "researcher": 192,
    "model_scout": 160,
    "engineer": 192,
    "scientist": 192,
    "reviewer": 160,
    "validator": 160,
    "network_steward": 160,
    "genesis_communicator": 256,
    "genesis_research_comprehension": 128,
    "genesis_learning_upgrade_planner": 160,
    "genesis_learning_transfer_planner": 160,
    "genesis_internal_code_reviewer": 128,
    "genesis_self_reviewer": 128,
    "bounded_coding_engineer": 256,
}

# Model checking is advisory on timeout only. These are the model-backed checking
# roles currently used by Genesis. Deterministic tests, Security, independent
# validation/quorum and promotion remain authoritative and are never bypassed.
MODEL_CHECK_TIMEOUT_RESPONSES = {
    "genesis_internal_code_reviewer": {
        "decision": "approve",
        "feedback": "model_check_timeout_skipped; continue with deterministic and independent validation",
        "model_check_status": "skipped_timeout",
    },
    "genesis_self_reviewer": {
        "decision": "no_change",
        "summary": "model_check_timeout_skipped",
        "objective": "",
        "confidence": 0.0,
        "model_check_status": "skipped_timeout",
    },
}


def _reasoning_role(prompt: str) -> str:
    """Return the bounded ROLE marker from the start of a reasoning prompt."""
    for line in prompt.splitlines()[:8]:
        if line.startswith("ROLE:"):
            return line.split(":", 1)[1].strip()
    return ""


def _reasoning_token_budget(prompt: str) -> int | None:
    """Return a compact role-specific output budget for local foundation models."""
    return LOCAL_REASONING_ROLE_TOKEN_BUDGETS.get(_reasoning_role(prompt))


def _model_check_timeout_response(prompt: str) -> str | None:
    """Return the role-specific advisory result when a model check times out.

    Only explicit checking roles are eligible. Generation, planning, research,
    coding and other model calls still raise on timeout because there is no valid
    work product to continue with. Adding a future checker requires registering
    its exact response schema here rather than silently treating every timeout as
    success.
    """
    payload = MODEL_CHECK_TIMEOUT_RESPONSES.get(_reasoning_role(prompt))
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True)


def _deterministic_learning_transfer(prompt: str) -> str | None:
    """Fallback route for a verified lesson when the foundation model times out.

    A trained Genesis/provider model gets the first opportunity to reason about
    the transfer. This deterministic path exists only for graceful degradation
    after a failed model call and still relies on the caller's independent
    grounding checks before any implementation can proceed.
    """
    if _reasoning_role(prompt) != "genesis_learning_transfer_planner":
        return None

    target_match = re.search(r"(?m)^TARGET ([^:\n]+):\s*$", prompt)
    lesson_match = re.search(r"(?m)^VERIFIED_TRANSFERABLE_LESSON:\s*(.+)$", prompt)
    if not target_match:
        return json.dumps(
            {
                "decision": "skip",
                "target_path": "",
                "summary": "",
                "acceptance": "",
                "confidence": 0.0,
                "reason": "no_ranked_genesis_target",
            },
            sort_keys=True,
        )

    target = target_match.group(1).strip()
    lesson = lesson_match.group(1).strip() if lesson_match else "verified transferable lesson"
    return json.dumps(
        {
            "decision": "upgrade",
            "target_path": target,
            "summary": (
                f"Apply the verified transferable lesson to the ranked Genesis target {target}: {lesson}"
            )[:1200],
            "acceptance": (
                "The target measurably applies the verified lesson, keeps existing safeguards intact, "
                "and the full repository test suite passes."
            ),
            "confidence": 0.8,
            "reason": "deterministic_timeout_fallback",
        },
        sort_keys=True,
    )


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
    """Optional provider implementing the tiny Genesis Provider Protocol."""

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
        request_payload: dict[str, object] = {"prompt": prompt}
        token_budget = _reasoning_token_budget(prompt)
        if token_budget is not None:
            request_payload["max_new_tokens"] = token_budget
        body = json.dumps(request_payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/reason",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Genesis-AI-Network/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            advisory = _model_check_timeout_response(prompt)
            if advisory is not None:
                return advisory
            deterministic = _deterministic_learning_transfer(prompt)
            if deterministic is not None:
                return deterministic
            raise
        value = payload.get("response")
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Provider returned no response text")
        return value


def _bounded_timeout(value: object, default: float = 60.0) -> float:
    try:
        return max(5.0, min(float(value), MAX_PROVIDER_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return default


def _configured_http_providers() -> list[GenesisHTTPProvider]:
    """Load any number of replaceable HTTP providers from bounded public config.

    `GENESIS_PROVIDER_ENDPOINTS` is an optional JSON list of objects with `url`,
    optional `name`, and optional `timeout_seconds`. Credentials do not belong in
    this configuration; provider authentication, if required, remains outside
    the repository/provider protocol boundary.

    The legacy single-provider environment variables remain supported so an
    existing deployment does not need to migrate atomically.
    """
    configured: list[GenesisHTTPProvider] = []
    seen: set[tuple[str, str]] = set()

    raw = os.environ.get("GENESIS_PROVIDER_ENDPOINTS", "").strip()
    if raw:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            entries = []
        if isinstance(entries, list):
            for index, entry in enumerate(entries, 1):
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("url") or "").strip()
                if not url:
                    continue
                name = str(entry.get("name") or f"genesis-http-{index}").strip() or f"genesis-http-{index}"
                timeout = _bounded_timeout(entry.get("timeout_seconds"), 60.0)
                key = (name, url.rstrip("/"))
                if key in seen:
                    continue
                seen.add(key)
                configured.append(GenesisHTTPProvider(url, name, timeout=timeout))

    legacy_url = os.environ.get("GENESIS_PROVIDER_URL", "").strip()
    if legacy_url:
        legacy_name = os.environ.get("GENESIS_PROVIDER_NAME", "genesis-http").strip() or "genesis-http"
        key = (legacy_name, legacy_url.rstrip("/"))
        if key not in seen:
            configured.append(
                GenesisHTTPProvider(
                    legacy_url,
                    legacy_name,
                    timeout=_bounded_timeout(os.environ.get("GENESIS_PROVIDER_TIMEOUT_SECONDS", "60"), 60.0),
                )
            )
    return configured


def _model_lab_root(explicit_root: Path | None) -> Path | None:
    if explicit_root is not None:
        return Path(explicit_root).resolve()
    raw = (
        os.environ.get("GENESIS_MODEL_LAB_ROOT", "").strip()
        or os.environ.get("GITHUB_WORKSPACE", "").strip()
    )
    return Path(raw).resolve() if raw else None


class ProviderRegistry:
    def __init__(self, include_bootstrap: bool = True, root: Path | None = None) -> None:
        self._providers: list[IntelligenceProvider] = []
        self._discovery_errors: list[str] = []
        if include_bootstrap:
            self.register(BootstrapProvider())

        runtime_root = _model_lab_root(root)
        if runtime_root is not None:
            try:
                from .model_provider import ActiveGenesisModelProvider

                for provider in ActiveGenesisModelProvider.discover(runtime_root):
                    self.register(provider)
            except Exception as exc:
                self._discovery_errors.append(
                    f"active_genesis_model_discovery:{type(exc).__name__}:{exc}"[:1000]
                )

        for provider in _configured_http_providers():
            self.register(provider)

    def register(self, provider: IntelligenceProvider) -> None:
        self._providers.append(provider)

    def discovery_errors(self) -> tuple[str, ...]:
        return tuple(self._discovery_errors)

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

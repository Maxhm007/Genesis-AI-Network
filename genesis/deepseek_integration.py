from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .providers import MAX_PROVIDER_TIMEOUT_SECONDS, ProviderRegistry


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_TIMEOUT_SECONDS = 90.0
DEFAULT_DEEPSEEK_MAX_TOKENS = 512
MAX_DEEPSEEK_MAX_TOKENS = 768
_ALLOWED_THINKING = {"enabled", "disabled"}
_ALLOWED_REASONING_EFFORT = {"low", "high", "max"}
_INSTALL_MARKER = "_genesis_deepseek_provider_installed"
_ORIGINAL_REGISTRY_INIT = ProviderRegistry.__init__


def _bounded_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(float(value), maximum))
    except (TypeError, ValueError):
        return default


def _bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _normalized_base_url(value: object) -> str:
    base_url = str(value or DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")
    if not base_url:
        return DEFAULT_DEEPSEEK_BASE_URL
    if base_url == DEFAULT_DEEPSEEK_BASE_URL or base_url.startswith("https://"):
        return base_url
    # Never send an API credential over plaintext HTTP. A custom compatible
    # endpoint remains possible, but it must provide TLS.
    return DEFAULT_DEEPSEEK_BASE_URL


class DeepSeekProvider:
    """Optional DeepSeek intelligence provider behind Genesis's existing gateway.

    The provider has no identity or promotion authority. It only supplies candidate
    reasoning/coding/review output through the same bounded provider abstraction
    already used by Genesis. Qwen and every existing provider keep their current
    routing behavior; DeepSeek is simply another eligible non-bootstrap provider.
    """

    capabilities = ("reasoning", "coding", "research", "planning", "review")

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        timeout: float = DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_DEEPSEEK_MAX_TOKENS,
        thinking: str = "enabled",
        reasoning_effort: str = "high",
    ) -> None:
        self.api_key = str(api_key).strip()
        self.model = str(model).strip() or DEFAULT_DEEPSEEK_MODEL
        self.base_url = _normalized_base_url(base_url)
        self.timeout = _bounded_float(
            timeout,
            DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
            minimum=5.0,
            maximum=MAX_PROVIDER_TIMEOUT_SECONDS,
        )
        self.max_tokens = _bounded_int(
            max_tokens,
            DEFAULT_DEEPSEEK_MAX_TOKENS,
            minimum=64,
            maximum=MAX_DEEPSEEK_MAX_TOKENS,
        )
        self.thinking = thinking if thinking in _ALLOWED_THINKING else "enabled"
        self.reasoning_effort = reasoning_effort if reasoning_effort in _ALLOWED_REASONING_EFFORT else "high"
        self.name = f"deepseek:{self.model}"
        self.resource_cost = 0.8
        self.reliability = 0.84

    @classmethod
    def from_env(cls) -> "DeepSeekProvider | None":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key,
            model=os.environ.get("GENESIS_DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=os.environ.get("GENESIS_DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            timeout=_bounded_float(
                os.environ.get("GENESIS_DEEPSEEK_TIMEOUT_SECONDS"),
                DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
                minimum=5.0,
                maximum=MAX_PROVIDER_TIMEOUT_SECONDS,
            ),
            max_tokens=_bounded_int(
                os.environ.get("GENESIS_DEEPSEEK_MAX_TOKENS"),
                DEFAULT_DEEPSEEK_MAX_TOKENS,
                minimum=64,
                maximum=MAX_DEEPSEEK_MAX_TOKENS,
            ),
            thinking=os.environ.get("GENESIS_DEEPSEEK_THINKING", "enabled").strip().lower(),
            reasoning_effort=os.environ.get("GENESIS_DEEPSEEK_REASONING_EFFORT", "high").strip().lower(),
        )

    def available(self) -> bool:
        # Avoid a network/API call during every provider registry scan. A present
        # credential means the provider is configured; transport/auth failures are
        # reported by reason() and remain ordinary provider failures.
        return bool(self.api_key)

    def reason(self, prompt: str) -> str:
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("prompt is required")
        if not self.api_key:
            raise RuntimeError("DeepSeek provider is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a replaceable intelligence provider for Genesis AI Network. "
                        "You do not define Genesis identity or authority. Return concise, testable, "
                        "evidence-aware output and preserve all stated safety and validation boundaries."
                    ),
                },
                {"role": "user", "content": prompt[:14000]},
            ],
            "stream": False,
            "max_tokens": self.max_tokens,
            "thinking": {"type": self.thinking},
            "reasoning_effort": self.reasoning_effort,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Genesis-AI-Network/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"DeepSeek API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("DeepSeek API transport failed") from exc

        choices = result.get("choices") if isinstance(result, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("DeepSeek API returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("DeepSeek API returned no response text")
        return content.strip()

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "available": self.available(),
            "capabilities": list(self.capabilities),
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "provider_independent": True,
            "credentials_in_repository": False,
        }


def _registry_init_with_deepseek(self: ProviderRegistry, *args, **kwargs) -> None:
    _ORIGINAL_REGISTRY_INIT(self, *args, **kwargs)
    provider = DeepSeekProvider.from_env()
    if provider is None:
        return
    if any(getattr(existing, "name", None) == provider.name for existing in self._providers):
        return
    self.register(provider)


def install_deepseek_provider() -> None:
    """Add DeepSeek to ProviderRegistry without changing existing provider setup."""
    if getattr(ProviderRegistry, _INSTALL_MARKER, False):
        return
    ProviderRegistry.__init__ = _registry_init_with_deepseek
    setattr(ProviderRegistry, _INSTALL_MARKER, True)

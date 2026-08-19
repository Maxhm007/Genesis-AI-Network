from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from genesis.intelligence_router import IntelligenceRouter
from genesis.providers import ProviderRegistry


ROOT = Path(__file__).resolve().parents[1]


def _load_adapter():
    path = ROOT / "scripts" / "anthropic_reasoning_provider.py"
    spec = importlib.util.spec_from_file_location("genesis_anthropic_provider", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    status = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return prompt


def test_anthropic_adapter_uses_messages_api_contract(monkeypatch) -> None:
    module = _load_adapter()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"content": [{"type": "text", "text": "hello from Claude"}]})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    client = module.AnthropicReasoningClient("secret-test-key", model="claude-test", max_tokens=321)
    assert client.reason("solve this") == "hello from Claude"

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    headers = {key.lower(): value for key, value in request.header_items()}
    assert body["model"] == "claude-test"
    assert body["max_tokens"] == 321
    assert body["messages"] == [{"role": "user", "content": "solve this"}]
    assert headers["x-api-key"] == "secret-test-key"
    assert headers["anthropic-version"] == module.ANTHROPIC_VERSION


def test_anthropic_adapter_is_unavailable_without_key() -> None:
    module = _load_adapter()
    client = module.AnthropicReasoningClient("")
    assert client.available() is False


def test_demanding_coding_prefers_claude_but_routine_work_prefers_local() -> None:
    registry = ProviderRegistry(include_bootstrap=False)
    qwen = FakeProvider("qwen3-0.6b-local")
    claude = FakeProvider("claude-sonnet")
    registry.register(qwen)
    registry.register(claude)
    router = IntelligenceRouter(registry)

    hard = router.select("coding", complexity=0.75, require_non_bootstrap=True)
    routine = router.select("coding", complexity=0.3, require_non_bootstrap=True)

    assert hard.provider is claude
    assert hard.reason.startswith("reliability-first")
    assert routine.provider is qwen
    assert routine.reason.startswith("resource-first")

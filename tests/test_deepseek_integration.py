import json

from genesis.deepseek_integration import DeepSeekProvider
from genesis.intelligence_router import IntelligenceRouter
from genesis.providers import ProviderRegistry


class QwenProvider:
    name = "qwen3-0.6b-local"
    capabilities = ("reasoning", "coding", "research", "planning", "review")
    reliability = 0.72
    resource_cost = 1.0

    def __init__(self, available=True):
        self._available = available

    def available(self):
        return self._available

    def reason(self, prompt):
        return "qwen"


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_deepseek_is_not_registered_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    registry = ProviderRegistry(include_bootstrap=False)
    assert all("deepseek" not in provider.name for provider in registry._providers)


def test_deepseek_registers_without_changing_existing_provider_configuration(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("GENESIS_DEEPSEEK_MODEL", "deepseek-v4-flash")
    registry = ProviderRegistry(include_bootstrap=False)
    deepseek = [provider for provider in registry._providers if "deepseek" in provider.name]
    assert len(deepseek) == 1
    assert deepseek[0].model == "deepseek-v4-flash"
    assert deepseek[0].capabilities == ("reasoning", "coding", "research", "planning", "review")


def test_general_router_keeps_qwen_preferred_when_both_are_available(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(QwenProvider())
    decision = IntelligenceRouter(registry).select("reasoning", complexity=0.6)
    assert decision.provider.name == "qwen3-0.6b-local"


def test_general_router_uses_deepseek_when_qwen_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(QwenProvider(available=False))
    decision = IntelligenceRouter(registry).select("reasoning", complexity=0.6)
    assert decision.provider.name == "deepseek:deepseek-v4-flash"


def test_deepseek_reason_uses_official_openai_compatible_chat_api(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": "review complete"}}]})

    monkeypatch.setattr("genesis.deepseek_integration.urllib.request.urlopen", fake_urlopen)
    provider = DeepSeekProvider("secret", model="deepseek-v4-flash")
    result = provider.reason("ROLE: reviewer\nOBJECTIVE: review this candidate")

    assert result == "review complete"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["thinking"] == {"type": "enabled"}
    assert captured["payload"]["reasoning_effort"] == "high"
    assert captured["payload"]["stream"] is False


def test_deepseek_status_never_exposes_api_key():
    provider = DeepSeekProvider("super-secret")
    status = provider.status()
    assert "super-secret" not in json.dumps(status, sort_keys=True)
    assert status["credentials_in_repository"] is False

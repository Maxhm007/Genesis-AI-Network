from genesis.intelligence_router import IntelligenceRouter
from genesis.providers import ProviderRegistry


class CheapProvider:
    name = "qwen3-0.6b-local"
    def available(self): return True
    def reason(self, prompt): return "ok"


class ExpensiveProvider:
    name = "frontier-like-provider"
    def available(self): return True
    def reason(self, prompt): return "ok"


def test_router_prefers_lower_resource_provider_when_sufficient():
    registry = ProviderRegistry(include_bootstrap=False)
    registry.register(ExpensiveProvider())
    registry.register(CheapProvider())
    decision = IntelligenceRouter(registry).select("coding", complexity=0.6)
    assert decision.provider.name == "qwen3-0.6b-local"


def test_router_can_exclude_bootstrap_for_complex_work():
    registry = ProviderRegistry(include_bootstrap=True)
    registry.register(CheapProvider())
    decision = IntelligenceRouter(registry).select("research", complexity=0.8, require_non_bootstrap=True)
    assert decision.provider.name == "qwen3-0.6b-local"

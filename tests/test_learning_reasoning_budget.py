from __future__ import annotations

import json

import genesis.providers as providers


def test_learning_roles_get_small_output_budgets() -> None:
    assert providers._reasoning_token_budget("ROLE: genesis_research_comprehension\nX") == 128
    assert providers._reasoning_token_budget("ROLE: genesis_learning_transfer_planner\nX") == 160
    assert providers._reasoning_token_budget("ROLE: genesis_learning_upgrade_planner\nX") == 160


def test_non_learning_roles_keep_provider_default_budget() -> None:
    assert providers._reasoning_token_budget("ROLE: engineer\nX") is None
    assert providers._reasoning_token_budget("OBJECTIVE: no role\nX") is None


def test_http_provider_sends_budget_only_for_learning_roles(monkeypatch) -> None:
    captured: list[dict] = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"response":"{}"}'

    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    provider = providers.GenesisHTTPProvider("http://127.0.0.1:8766", timeout=60)

    provider.reason("ROLE: genesis_research_comprehension\nReturn JSON")
    provider.reason("ROLE: engineer\nReturn JSON")

    assert captured[0]["max_new_tokens"] == 128
    assert captured[0]["prompt"].startswith("ROLE: genesis_research_comprehension")
    assert "max_new_tokens" not in captured[1]

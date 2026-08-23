from __future__ import annotations

import json

import genesis.providers as providers


def test_cognitive_roles_get_bounded_output_budgets() -> None:
    assert providers._reasoning_token_budget("ROLE: genesis_research_comprehension\nX") == 128
    assert providers._reasoning_token_budget("ROLE: genesis_learning_transfer_planner\nX") == 160
    assert providers._reasoning_token_budget("ROLE: genesis_learning_upgrade_planner\nX") == 160
    assert providers._reasoning_token_budget("ROLE: engineer\nX") == 192
    assert providers._reasoning_token_budget("ROLE: bounded_coding_engineer\nX") == 256


def test_unknown_roles_keep_provider_default_budget() -> None:
    assert providers._reasoning_token_budget("ROLE: unknown_specialist\nX") is None
    assert providers._reasoning_token_budget("OBJECTIVE: no role\nX") is None


def test_deterministic_transfer_uses_first_ranked_target_as_timeout_fallback() -> None:
    prompt = (
        "ROLE: genesis_learning_transfer_planner\n"
        "VERIFIED_CAPABILITY_DOMAINS: agent_reasoning\n"
        "VERIFIED_TRANSFERABLE_LESSON: Agents improve when tool arguments are grounded in context.\n"
        "VERIFIED_TOPICS: agent, tool use, grounding\n"
        "GENESIS_TARGETS:\n"
        "TARGET genesis/first.py:\n"
        "def first():\n    return True\n\n"
        "TARGET genesis/second.py:\n"
        "def second():\n    return True\n"
    )

    payload = json.loads(providers._deterministic_learning_transfer(prompt) or "{}")

    assert payload["decision"] == "upgrade"
    assert payload["target_path"] == "genesis/first.py"
    assert payload["reason"] == "deterministic_timeout_fallback"
    assert "tool arguments are grounded" in payload["summary"]


def test_http_provider_calls_model_for_transfer_role(monkeypatch) -> None:
    captured: list[dict] = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"response":"{\\"decision\\":\\"skip\\",\\"reason\\":\\"model_considered_transfer\\"}"}'

    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    provider = providers.GenesisHTTPProvider("http://127.0.0.1:8766", timeout=60)

    transfer = provider.reason(
        "ROLE: genesis_learning_transfer_planner\n"
        "VERIFIED_TRANSFERABLE_LESSON: Ground tool arguments from context.\n"
        "GENESIS_TARGETS:\nTARGET genesis/tooling.py:\ndef route():\n    return True\n"
    )
    provider.reason("ROLE: genesis_research_comprehension\nReturn JSON")
    provider.reason("ROLE: engineer\nReturn JSON")

    transfer_payload = json.loads(transfer)
    assert transfer_payload["reason"] == "model_considered_transfer"
    assert len(captured) == 3
    assert captured[0]["max_new_tokens"] == 160
    assert captured[0]["prompt"].startswith("ROLE: genesis_learning_transfer_planner")
    assert captured[1]["max_new_tokens"] == 128
    assert captured[2]["max_new_tokens"] == 192


def test_transfer_timeout_uses_deterministic_fallback(monkeypatch) -> None:
    def fake_urlopen(_request, timeout=None):
        raise TimeoutError("model timed out")

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    provider = providers.GenesisHTTPProvider("http://127.0.0.1:8766", timeout=60)

    transfer = provider.reason(
        "ROLE: genesis_learning_transfer_planner\n"
        "VERIFIED_TRANSFERABLE_LESSON: Ground tool arguments from context.\n"
        "GENESIS_TARGETS:\nTARGET genesis/tooling.py:\ndef route():\n    return True\n"
    )

    payload = json.loads(transfer)
    assert payload["decision"] == "upgrade"
    assert payload["target_path"] == "genesis/tooling.py"
    assert payload["reason"] == "deterministic_timeout_fallback"

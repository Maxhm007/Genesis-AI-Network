import json
from unittest.mock import patch

import pytest

from genesis.providers import GenesisHTTPProvider


def _timeout_provider() -> GenesisHTTPProvider:
    return GenesisHTTPProvider("http://127.0.0.1:8766", name="test-model", timeout=60)


def test_internal_code_review_timeout_is_advisory() -> None:
    provider = _timeout_provider()
    prompt = "ROLE: genesis_internal_code_reviewer\nOBJECTIVE: review candidate\n"

    with patch("genesis.providers.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        payload = json.loads(provider.reason(prompt))

    assert payload["decision"] == "approve"
    assert payload["model_check_status"] == "skipped_timeout"
    assert "deterministic and independent validation" in payload["feedback"]


def test_file_self_review_timeout_is_skipped() -> None:
    provider = _timeout_provider()
    prompt = "ROLE: genesis_self_reviewer\nFILE: genesis/example.py\n"

    with patch("genesis.providers.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        payload = json.loads(provider.reason(prompt))

    assert payload["decision"] == "no_change"
    assert payload["model_check_status"] == "skipped_timeout"
    assert payload["summary"] == "model_check_timeout_skipped"


def test_generation_timeout_is_not_ignored() -> None:
    provider = _timeout_provider()
    prompt = "ROLE: bounded_coding_engineer\nOBJECTIVE: produce code\n"

    with patch("genesis.providers.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(TimeoutError, match="timed out"):
            provider.reason(prompt)

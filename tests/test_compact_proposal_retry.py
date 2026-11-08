"""Regression coverage for Issue #386 provider protocol failures."""
from __future__ import annotations

import json

from genesis.coding import CodingModule
from genesis.compact_proposal_retry import _compact_retry_feedback
from genesis.providers import ProviderRegistry


def _module(tmp_path):
    target = tmp_path / "genesis" / "learned_capabilities.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    return CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False)), target


def test_oversized_full_file_retries_as_small_edit(tmp_path):
    module, target = _module(tmp_path)

    class Provider:
        name = "synthetic-oversized-coder"

        def __init__(self):
            self.prompts = []

        def reason(self, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return json.dumps({"files": {"genesis/learned_capabilities.py": "A" * 81000}})
            assert "COMPACT_SIZE_RECOVERY" in prompt
            assert "MAX_EDIT_BYTES" in prompt
            assert "Do NOT emit a files mapping" in prompt
            return json.dumps({"edits": [{
                "path": "genesis/learned_capabilities.py",
                "start_line": 1, "end_line": 1, "new": "VALUE = 2"
            }]})

    provider = Provider()
    result = module.propose("Update the existing VALUE assignment", ["genesis/learned_capabilities.py"], provider=provider)
    assert len(provider.prompts) == 2
    assert result.files["genesis/learned_capabilities.py"] == "VALUE = 2\n"
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert module.MAX_TOTAL_BYTES == 80000


def test_malformed_json_retries_using_valid_compact_json(tmp_path):
    module, target = _module(tmp_path)

    class Provider:
        name = "synthetic-malformed-json-coder"
        prompts = []

        def reason(self, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return '{"edits":[{"path":"genesis/learned_capabilities.py","start_line":1,"end_line":1,"new":"""VALUE = 2"""}]}'
            assert "COMPACT_JSON_RECOVERY" in prompt
            assert "ONE JSON object" in prompt
            return json.dumps({"edits": [{
                "path": "genesis/learned_capabilities.py",
                "start_line": 1, "end_line": 1, "new": "VALUE = 2"
            }]})

    provider = Provider()
    result = module.propose("Update VALUE", ["genesis/learned_capabilities.py"], provider=provider)
    assert len(provider.prompts) == 2
    assert result.files["genesis/learned_capabilities.py"] == "VALUE = 2\n"
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_size_guidance_does_not_raise_limits(tmp_path):
    module, _ = _module(tmp_path)
    feedback = _compact_retry_feedback(module, "", ValueError("coding proposal exceeds byte limit"))
    assert "COMPACT_SIZE_RECOVERY" in feedback
    assert str(module.MAX_EDIT_BYTES) in feedback
    assert "do not truncate code mechanically" in feedback.lower()
    assert _compact_retry_feedback(module, "", ValueError("coding proposal creates invalid Python syntax")) == ""

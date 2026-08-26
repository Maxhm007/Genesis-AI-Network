from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_provider_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "local_reasoning_provider.py"
    spec = importlib.util.spec_from_file_location("genesis_local_reasoning_provider_compact", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_coding_prompt_uses_quote_free_one_edit_protocol():
    module = _load_provider_module()
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        "OUTPUT: JSON only in this shape: "
        '{"edits":[{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"replacement text"}]}\n'
        'VALID_PATHS: ["genesis/example.py"]\n'
    )

    simplified = module.simplify_bounded_coding_prompt(prompt)

    assert "do not use JSON" in simplified
    assert "PATH: genesis/example.py" in simplified
    assert "START: 5" in simplified
    assert "END: 5" in simplified
    assert "NEW:\nreplacement text\nEND_NEW" in simplified
    assert '{"edits":[' not in simplified


def test_compact_edit_normalizes_to_existing_json_contract_without_escaping_risk():
    module = _load_provider_module()
    raw = (
        "PATH: genesis/example.py\n"
        "START: 5\n"
        "END: 5\n"
        "NEW:\n"
        'VALUE = {"quoted": "code"}\n'
        "END_NEW"
    )

    normalized = module.normalize_bounded_coding_output(raw)
    payload = json.loads(normalized)

    assert payload == {
        "path": "genesis/example.py",
        "start_line": 5,
        "end_line": 5,
        "new": 'VALUE = {"quoted": "code"}',
    }
    assert module.bounded_coding_output_complete(raw) is True


def test_malformed_compact_edit_is_not_repaired_or_invented():
    module = _load_provider_module()
    raw = (
        "PATH: genesis/example.py\n"
        "START: 5\n"
        "END: 5\n"
        "NEW:\n"
        "VALUE = 8"
    )

    assert module.normalize_bounded_coding_output(raw) == raw
    assert module.bounded_coding_output_complete(raw) is False


def test_compact_edit_can_use_bounded_completion_reserve_when_truncated():
    module = _load_provider_module()
    partial = (
        "PATH: genesis/example.py\n"
        "START: 5\n"
        "END: 5\n"
        "NEW:\n"
        "VALUE = 8"
    )

    assert module.json_completion_reserve_tokens(
        partial,
        generated_tokens=128,
        requested_budget=128,
        configured_budget=160,
    ) == 32


def test_legacy_json_output_remains_accepted_unchanged():
    module = _load_provider_module()
    raw = '{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"VALUE = 8"}'

    assert module.normalize_bounded_coding_output(raw) == raw
    assert module.bounded_coding_output_complete(raw) is True

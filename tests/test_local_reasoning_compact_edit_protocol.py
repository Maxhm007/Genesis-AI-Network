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


def test_bounded_coding_prompt_uses_single_line_one_edit_protocol():
    module = _load_provider_module()
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        "OUTPUT: JSON only in this shape: "
        '{"edits":[{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"replacement text"}]}\n'
        'VALID_PATHS: ["genesis/example.py"]\n'
    )

    simplified = module.simplify_bounded_coding_prompt(prompt)

    assert "do not use JSON" in simplified
    assert "EDIT|genesis/example.py|5|5|replacement text" in simplified
    assert "then a newline" in simplified
    assert '{"edits":[' not in simplified


def test_single_line_edit_normalizes_quotes_braces_and_pipes_without_json_escaping():
    module = _load_provider_module()
    raw = 'EDIT|genesis/example.py|5|5|VALUE = {"quoted": "code|safe"}\n'

    normalized = module.normalize_bounded_coding_output(raw)
    payload = json.loads(normalized)

    assert payload == {
        "path": "genesis/example.py",
        "start_line": 5,
        "end_line": 5,
        "new": 'VALUE = {"quoted": "code|safe"}',
    }
    assert module.bounded_coding_output_complete(raw) is True


def test_single_line_edit_without_newline_is_not_treated_as_generation_complete():
    module = _load_provider_module()
    raw = "EDIT|genesis/example.py|5|5|VALUE = 8"

    assert module.bounded_coding_output_complete(raw) is False
    assert module.normalize_bounded_coding_output(raw) == raw


def test_single_line_edit_can_be_accepted_without_newline_only_after_safe_early_termination():
    module = _load_provider_module()
    raw = "EDIT|genesis/example.py|5|5|VALUE = 8"

    normalized = module.normalize_bounded_coding_output(
        raw,
        allow_unterminated_single_line=True,
    )
    assert json.loads(normalized) == {
        "path": "genesis/example.py",
        "start_line": 5,
        "end_line": 5,
        "new": "VALUE = 8",
    }


def test_malformed_single_line_edit_is_not_repaired_or_invented():
    module = _load_provider_module()
    raw = "EDIT|genesis/example.py|five|5|VALUE = 8\n"

    assert module.normalize_bounded_coding_output(raw) == raw
    assert module.bounded_coding_output_complete(raw) is False


def test_older_multiline_compact_protocol_remains_accepted():
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
    assert payload["new"] == 'VALUE = {"quoted": "code"}'
    assert module.bounded_coding_output_complete(raw) is True


def test_legacy_json_output_remains_accepted_unchanged():
    module = _load_provider_module()
    raw = '{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"VALUE = 8"}'

    assert module.normalize_bounded_coding_output(raw) == raw
    assert module.bounded_coding_output_complete(raw) is True

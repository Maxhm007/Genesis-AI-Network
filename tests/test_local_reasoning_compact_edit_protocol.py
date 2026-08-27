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


def test_bounded_coding_prompt_prefers_explicitly_terminated_multiline_protocol():
    module = _load_provider_module()
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        "OUTPUT: JSON only in this shape: "
        '{"edits":[{"path":"genesis/example.py","start_line":5,"end_line":5,"new":"replacement text"}]}\n'
        'VALID_PATHS: ["genesis/example.py"]\n'
    )

    simplified = module.simplify_bounded_coding_prompt(prompt)

    assert "do not use JSON" in simplified
    assert "EDIT_BLOCK|genesis/example.py|5|5" in simplified
    assert "replacement text\nEND_EDIT" in simplified
    assert "END_EDIT must be on its own final line" in simplified
    assert '{"edits":[' not in simplified


def test_multiline_edit_normalizes_complete_python_with_quotes_braces_and_pipes():
    module = _load_provider_module()
    raw = (
        "EDIT_BLOCK|genesis/example.py|5|7\n"
        "value = (\n"
        '    {"quoted": "code|safe"}\n'
        ")\n"
        "END_EDIT"
    )

    normalized = module.normalize_bounded_coding_output(raw)
    payload = json.loads(normalized)

    assert payload == {
        "path": "genesis/example.py",
        "start_line": 5,
        "end_line": 7,
        "new": 'value = (\n    {"quoted": "code|safe"}\n)',
    }
    assert module.bounded_coding_output_complete(raw) is True


def test_multiline_edit_does_not_complete_at_internal_newline():
    module = _load_provider_module()
    raw = (
        "EDIT_BLOCK|genesis/example.py|5|7\n"
        "value = (\n"
        '    {"quoted": "code|safe"}\n'
    )

    assert module.bounded_coding_output_complete(raw) is False
    assert module.normalize_bounded_coding_output(raw) == raw


def test_multiline_edit_missing_terminator_fails_closed_even_if_python_looks_complete():
    module = _load_provider_module()
    raw = (
        "EDIT_BLOCK|genesis/example.py|5|7\n"
        "value = (\n"
        "    8\n"
        ")"
    )

    assert module.bounded_coding_output_complete(raw) is False
    assert module.normalize_bounded_coding_output(raw) == raw


def test_multiline_edit_rejects_malformed_range_without_repairing_it():
    module = _load_provider_module()
    raw = (
        "EDIT_BLOCK|genesis/example.py|five|7\n"
        "value = 8\n"
        "END_EDIT"
    )

    assert module.bounded_coding_output_complete(raw) is False
    assert module.normalize_bounded_coding_output(raw) == raw


def test_retry_prompt_schema_is_converted_without_losing_following_guidance():
    module = _load_provider_module()
    prompt = (
        "ROLE: bounded_coding_engineer\n"
        'PREVIOUS: {"path":"genesis/previous.py","new":"diagnostic"}\n'
        'Return ONLY the same JSON shape as: {"edits":[{"path":"genesis/example.py","start_line":7,"end_line":8,"new":"replacement text"}]}. Verify the range before using it.\n'
    )

    simplified = module.simplify_bounded_coding_prompt(prompt)

    assert 'PREVIOUS: {"path":"genesis/previous.py","new":"diagnostic"}' in simplified
    assert "EDIT_BLOCK|genesis/example.py|7|8" in simplified
    assert "replacement text\nEND_EDIT" in simplified
    assert ". Verify the range before using it." in simplified


def test_single_line_edit_remains_accepted_for_compatibility():
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

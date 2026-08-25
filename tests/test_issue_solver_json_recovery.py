import json

import pytest

from genesis.issue_solver import IssueSolver


def test_extract_json_accepts_exact_object():
    payload = IssueSolver._extract_json('{"title":"fix","files":{"genesis/x.py":"x = 1\\n"}}')
    assert payload["title"] == "fix"


def test_extract_json_accepts_fenced_object():
    payload = IssueSolver._extract_json('```json\n{"title":"fix","files":{"genesis/x.py":"x = 1\\n"}}\n```')
    assert payload["files"] == {"genesis/x.py": "x = 1\n"}


def test_extract_json_recovers_object_after_model_preamble():
    raw = 'I will return the bounded repair now.\n{"title":"fix","files":{"genesis/x.py":"x = 1\\n"}}'
    payload = IssueSolver._extract_json(raw)
    assert payload["title"] == "fix"


def test_extract_json_ignores_invalid_brace_before_valid_object_and_trailing_text():
    raw = 'Note {not json}. Final:\n{"title":"fix","files":{"genesis/x.py":"x = 1\\n"}}\nDone.'
    payload = IssueSolver._extract_json(raw)
    assert payload["files"] == {"genesis/x.py": "x = 1\n"}


def test_extract_json_still_rejects_output_without_complete_json_object():
    with pytest.raises(json.JSONDecodeError):
        IssueSolver._extract_json('No structured repair was produced.')

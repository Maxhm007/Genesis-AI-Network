from __future__ import annotations

import pytest

from genesis.learned_capabilities import run_capability


SCHEMA = {
    "type": "object",
    "required": ["answer", "confidence", "tags"],
    "properties": {
        "answer": {"type": "string", "minLength": 1, "maxLength": 100},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "tags": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 20},
        },
    },
    "additionalProperties": False,
}


def test_structured_output_schema_parses_and_validates_json():
    result = run_capability(
        "structured_output_schema",
        '{"answer":"ok","confidence":0.9,"tags":["verified"]}',
        SCHEMA,
    )
    assert result == {"answer": "ok", "confidence": 0.9, "tags": ["verified"]}


def test_structured_output_schema_rejects_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        run_capability("structured_output_schema", '{"answer":', SCHEMA)


def test_structured_output_schema_rejects_missing_required_and_extra_fields():
    with pytest.raises(ValueError, match="missing required"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok", "confidence": 0.9},
            SCHEMA,
        )

    with pytest.raises(ValueError, match="unexpected field"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok", "confidence": 0.9, "tags": [], "extra": True},
            SCHEMA,
        )


def test_structured_output_schema_enforces_types_ranges_and_bounds():
    with pytest.raises(ValueError, match="expected number"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok", "confidence": "high", "tags": []},
            SCHEMA,
        )

    with pytest.raises(ValueError, match="above maximum"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok", "confidence": 1.2, "tags": []},
            SCHEMA,
        )

    with pytest.raises(ValueError, match="too many items"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok", "confidence": 0.5, "tags": ["a", "b", "c", "d"]},
            SCHEMA,
        )


def test_structured_output_schema_rejects_unsupported_schema_keywords():
    with pytest.raises(ValueError, match="unsupported schema keyword"):
        run_capability(
            "structured_output_schema",
            {"answer": "ok"},
            {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "patternProperties": {},
            },
        )


def test_structured_output_schema_bounds_json_size_and_depth():
    with pytest.raises(ValueError, match="JSON size bound"):
        run_capability(
            "structured_output_schema",
            '{"answer":"too long"}',
            {"type": "object"},
            max_json_chars=5,
        )

    with pytest.raises(ValueError, match="depth bound"):
        run_capability(
            "structured_output_schema",
            {"a": {"b": {"c": 1}}},
            {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "object",
                        "properties": {
                            "b": {
                                "type": "object",
                                "properties": {"c": {"type": "integer"}},
                            }
                        },
                    }
                },
            },
            max_depth=1,
        )

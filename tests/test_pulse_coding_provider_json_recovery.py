from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_provider_module():
    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        path = scripts / "pulse_coding_provider.py"
        spec = importlib.util.spec_from_file_location("genesis_pulse_coding_provider_json_recovery", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_structural_json_recovery_closes_only_missing_containers():
    module = _load_provider_module()
    raw = (
        '{"edits":[{"path":"genesis/example.py","start_line":1,'
        '"end_line":1,"new":"VALUE = 8"}'
    )

    completed = module.AdaptiveCodingModel._complete_truncated_json(raw)

    assert completed is not None
    assert completed == raw + "]}"
    assert json.loads(completed) == {
        "edits": [
            {
                "path": "genesis/example.py",
                "start_line": 1,
                "end_line": 1,
                "new": "VALUE = 8",
            }
        ]
    }


def test_structural_json_recovery_does_not_invent_unfinished_value():
    module = _load_provider_module()
    raw = '{"edits":[{"path":"genesis/example.py","new":"VALUE = 8'

    assert module.AdaptiveCodingModel._complete_truncated_json(raw) is None


def test_provider_returns_recovered_json_before_coding_module_parses_it():
    module = _load_provider_module()
    raw = (
        '{"edits":[{"path":"genesis/example.py","start_line":1,'
        '"end_line":1,"new":"VALUE = 8"}]'
    )
    model = module.AdaptiveCodingModel("unused", None, max_new_tokens=128)
    model._reason_once = lambda prompt, max_new_tokens: raw

    result = model.reason("OBJECTIVE: bounded test")

    assert result == raw + "}"
    assert json.loads(result)["edits"][0]["path"] == "genesis/example.py"

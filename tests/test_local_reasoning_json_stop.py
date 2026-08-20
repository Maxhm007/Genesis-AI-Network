import importlib.util
from pathlib import Path


def _provider_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "local_reasoning_provider.py"
    spec = importlib.util.spec_from_file_location("genesis_local_reasoning_json_stop", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_balanced_json_completion_handles_nested_edits_and_string_braces():
    module = _provider_module()
    assert module.balanced_json_object_complete('prefix {"edits":[{"new":"if x: {value}"}]} suffix') is True
    assert module.balanced_json_object_complete('{"edits":[{"new":"partial"}]') is False
    assert module.balanced_json_object_complete('no json yet') is False


def test_balanced_json_completion_handles_escaped_quotes():
    module = _provider_module()
    text = r'{"edits":[{"new":"raise ValueError(\"bad {input}\")"}]}'
    assert module.balanced_json_object_complete(text) is True

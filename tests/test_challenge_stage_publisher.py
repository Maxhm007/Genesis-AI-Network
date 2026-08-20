import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "publish_challenge_stage.py"
    spec = importlib.util.spec_from_file_location("genesis_publish_challenge_stage", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_payload_records_run_identity_and_stage():
    module = _module()
    payload = module.stage_payload(
        stage="provider_ready",
        run_id="123",
        event="push",
        trigger_sha="abc",
    )
    assert payload["stage"] == "provider_ready"
    assert payload["run_id"] == "123"
    assert payload["event"] == "push"
    assert payload["trigger_sha"] == "abc"
    assert payload["timestamp"].endswith("+00:00")


def test_stage_payload_rejects_unknown_stage():
    module = _module()
    with pytest.raises(ValueError, match="unsupported challenge stage"):
        module.stage_payload(stage="mystery", run_id="1", event="push", trigger_sha="abc")

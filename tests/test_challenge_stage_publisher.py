import importlib.util
import subprocess
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


def test_only_explicit_challenge_diagnostics_escape_runtime_ignore(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / ".gitignore").write_text((root / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    public_runtime = tmp_path / "docs" / "runtime"
    public_runtime.mkdir(parents=True)
    allowed = [
        "GENESIS_CHALLENGE_STAGE.json",
        "GENESIS_CHALLENGE_LAST_RESULT.json",
        "GENESIS_PROVIDER_LAST_LOG.txt",
        "GENESIS_CHALLENGE_LAST_RUN.json",
    ]
    for name in allowed:
        (public_runtime / name).write_text("diagnostic\n", encoding="utf-8")
    (public_runtime / "OTHER_RUNTIME_STATE.json").write_text("private\n", encoding="utf-8")
    private_runtime = tmp_path / "runtime"
    private_runtime.mkdir()
    (private_runtime / "state.json").write_text("private\n", encoding="utf-8")

    for name in allowed:
        result = subprocess.run(
            ["git", "check-ignore", "-q", f"docs/runtime/{name}"],
            cwd=tmp_path,
            check=False,
        )
        assert result.returncode == 1, name

    assert subprocess.run(
        ["git", "check-ignore", "-q", "docs/runtime/OTHER_RUNTIME_STATE.json"],
        cwd=tmp_path,
        check=False,
    ).returncode == 0
    assert subprocess.run(
        ["git", "check-ignore", "-q", "runtime/state.json"],
        cwd=tmp_path,
        check=False,
    ).returncode == 0

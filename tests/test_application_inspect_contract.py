import json
from pathlib import Path

from genesis.application import ApplicationModule


def test_application_inspect_returns_module_and_target_status(tmp_path: Path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "mobile").mkdir()
    (tmp_path / "config" / "applications.json").write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "target_id": "android-mobile",
                        "platform": "android",
                        "source_root": "mobile",
                        "artifact": "apk",
                        "architecture": "mobile-client+authenticated-genesis-api",
                        "priority": 96,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = ApplicationModule(tmp_path).inspect()

    assert isinstance(result, dict)
    assert result["module"] == "genesis.application"
    assert len(result["targets"]) == 1
    assert result["targets"][0]["target_id"] == "android-mobile"
    assert result["targets"][0]["source_present"] is True
    assert result["targets"][0]["status"] == "present"

from pathlib import Path

from genesis.communication import GenesisCommunicator
from genesis.providers import ProviderRegistry


def test_genesis_replies_and_reports_capabilities(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    for name in ("communication.py", "selfdev.py", "promotion.py"):
        (tmp_path / "genesis" / name).write_text("# present\n", encoding="utf-8")
    communicator = GenesisCommunicator(tmp_path, ProviderRegistry(include_bootstrap=True))
    result = communicator.reply("tester", "What can you do now?")
    assert result["message"]["sender"] == "tester"
    assert result["message"]["message"] == "What can you do now?"
    assert result["provider"] == "genesis-bootstrap"
    assert result["genesis_response"]
    assert result["capability_summary"]["max_score"] == 100


def test_empty_message_is_rejected(tmp_path: Path):
    communicator = GenesisCommunicator(tmp_path, ProviderRegistry(include_bootstrap=True))
    try:
        communicator.reply("tester", "   ")
    except ValueError as exc:
        assert "message is required" in str(exc)
    else:
        raise AssertionError("empty message should be rejected")

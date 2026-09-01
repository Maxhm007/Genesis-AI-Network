from pathlib import Path


WORKFLOW = Path(".github/workflows/genesis-bounded-repair-worker.yml")


def test_bounded_repair_provider_has_only_required_permissions() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    permissions = text.split("permissions:", 1)[1].split("concurrency:", 1)[0]
    assert "contents: write" in permissions
    assert "issues: write" in permissions
    assert "actions: write" in permissions
    assert "pull-requests:" not in permissions
    assert "checks:" not in permissions


def test_bounded_repair_provider_is_local_replaceable_and_has_no_embedded_credentials() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "GENESIS_REPAIR_PROVIDER_URL: http://127.0.0.1:8766" in text
    assert "Qwen/Qwen2.5-Coder-0.5B-Instruct" in text
    assert "Qwen/Qwen2.5-Coder-1.5B-Instruct" in text
    assert "scripts/pulse_coding_provider.py" in text
    assert "sk-" not in text
    assert "api_key" not in text.lower()

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "coding-intelligence-pulse.yml"
PROTOCOL = ROOT / "PROVIDER_PROTOCOL.md"


def test_coding_pulse_keeps_qwen_primary_and_uses_local_deepseek_escalation():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Qwen/Qwen2.5-Coder-0.5B-Instruct" in workflow
    assert "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B" in workflow
    assert "GENESIS_PULSE_FALLBACK_MODEL" in workflow
    assert "GENESIS_PULSE_ESCALATION_MODEL" in workflow
    assert "snapshot_download" in workflow
    assert "--escalation-model \"$GENESIS_PULSE_ESCALATION_MODEL\"" in workflow


def test_local_deepseek_path_requires_no_api_key():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    protocol = PROTOCOL.read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY" not in workflow
    assert "deepseek-v4-flash" not in protocol
    assert "api.deepseek.com" not in protocol
    assert "DeepSeek-R1-Distill-Qwen-1.5B" in protocol
    assert "no DeepSeek API key" in protocol


def test_api_deepseek_module_was_removed():
    assert not (ROOT / "genesis" / "deepseek_integration.py").exists()

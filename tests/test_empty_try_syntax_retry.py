"""Issue #381 regression: reject comment-only try bodies and retry safely."""
import json

from genesis.coding import CodingModule
from genesis.providers import ProviderRegistry
from genesis.python_syntax_retry import _empty_try_block_guidance


BAD_TRY = (
    "        try:\n"
    "            # Existing code here\n"
    "        except Exception as e:\n"
    "            print(f'An error occurred: {e}')\n"
    "        assessments.sort()"
)


def test_empty_try_guidance_is_specific_and_bounded(tmp_path):
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    raw = json.dumps({"edits": [{
        "path": "genesis/immortality_scan.py",
        "start_line": 3,
        "end_line": 3,
        "new": BAD_TRY,
    }]})
    error = ValueError(
        "coding proposal creates invalid Python syntax in genesis/immortality_scan.py "
        "at 5:9: expected an indented block after 'try' statement"
    )
    guidance = _empty_try_block_guidance(module, raw, error)
    assert "EMPTY_TRY_BLOCK_RECOVERY" in guidance
    assert "NO executable body" in guidance
    assert "NUMBERED_CONTEXT" in guidance
    assert "# Existing code here" in guidance
    assert "Preserve existing statements" in guidance
    assert _empty_try_block_guidance(module, "not-json", error) == ""
    assert _empty_try_block_guidance(module, raw, ValueError("different error")) == ""


def test_provider_recovers_on_specific_empty_try_feedback(tmp_path):
    target = tmp_path / "genesis" / "immortality_scan.py"
    target.parent.mkdir()
    target.write_text(
        "def scan():\n"
        "    assessments = [3, 1]\n"
        "    assessments.sort()\n"
        "    return assessments\n",
        encoding="utf-8",
    )

    class Provider:
        name = "issue-381-syntax-retry"

        def __init__(self):
            self.prompts = []

        def reason(self, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                replacement = BAD_TRY
            else:
                assert "EMPTY_TRY_BLOCK_RECOVERY" in prompt
                assert "NO executable body" in prompt
                assert "AST_SAFE_STATEMENT_RANGE: genesis/immortality_scan.py:3-3" in prompt
                replacement = "assessments.sort(key=lambda item: item)"
            return json.dumps({"edits": [{
                "path": "genesis/immortality_scan.py",
                "start_line": 3,
                "end_line": 3,
                "new": replacement,
            }]})

    provider = Provider()
    module = CodingModule(tmp_path, ProviderRegistry(include_bootstrap=False))
    proposal = module.propose("Make assessments sorting deterministic", ["genesis/immortality_scan.py"], provider=provider)
    assert len(provider.prompts) == 2
    result = proposal.files["genesis/immortality_scan.py"]
    compile(result, "genesis/immortality_scan.py", "exec")
    assert "assessments.sort(key=lambda item: item)" in result
    assert "# Existing code here" not in result
    assert target.read_text(encoding="utf-8").count("assessments.sort()") == 1

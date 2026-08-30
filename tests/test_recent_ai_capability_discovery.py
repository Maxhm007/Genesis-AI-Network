from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "discover_recent_ai_capability.py"
spec = importlib.util.spec_from_file_location("recent_ai_capability_discovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_extract_candidate_and_dedupe():
    rows = module.extract_candidates(
        "example/ai",
        "v1",
        "2026-08-30T00:00:00Z",
        "https://github.com/example/ai/releases/tag/v1",
        "- Add verifier-guided reasoning with tool calling for autonomous agents\n"
        "- Fix documentation typo\n",
    )
    assert len(rows) == 1
    candidate = rows[0]
    assert "reasoning" in candidate.capability_name.lower()
    assert candidate.score >= module.MIN_RELEVANCE_SCORE

    duplicate_text = [
        f"<!-- genesis-capability-discovery:{candidate.fingerprint} --> already queued"
    ]
    assert module.choose_candidate(rows, [], duplicate_text) is None


def test_issue_body_matches_existing_capability_builder_contract():
    candidate = module.Candidate(
        source_repo="example/ai",
        release_name="v1",
        published_at="2026-08-30T00:00:00Z",
        source_url="https://github.com/example/ai/releases/tag/v1",
        statement="Add verifier-guided reasoning with tool calling",
        capability_name="verifier-guided reasoning with tool calling",
        fingerprint="0123456789abcdef",
        score=14,
        matched_needs=("reasoning", "tool calling", "verifier"),
    )
    body = module._issue_body(candidate)
    assert "<!-- genesis-task-id:task-0123456789abcdef -->" in body
    assert "- **Task type:** `new_capability`" in body
    assert "- **Source:** `genesis.evolution_learning`" in body
    assert "- **Target:** `genesis/learned_capabilities.py`" in body
    assert "verified transferable lesson" in body
    assert "Use the learned idea:" in body
    assert "External learning evidence:" in body
    assert "Target exactly genesis/learned_capabilities.py." in body

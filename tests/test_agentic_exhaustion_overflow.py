from pathlib import Path

import scripts.requeue_exhausted_issues as module


def _terminal_issue(number: int) -> dict:
    return {
        "number": number,
        "title": f"[Genesis Task] exhausted {number}",
        "body": "- **Target:** `genesis/example.py`\n",
        "state": "closed",
        "labels": [
            {"name": "genesis-solver-exhausted"},
            {"name": "genesis-deferred"},
        ],
    }


def test_overflow_terminal_exhaustion_waits_for_agentic_not_normal_requeue(
    monkeypatch, tmp_path: Path
):
    issues = [_terminal_issue(101), _terminal_issue(102), _terminal_issue(103)]
    calls: list[tuple[str, str, dict | None]] = []

    monkeypatch.setattr(module, "engine_generation", lambda root: "engine-test")
    monkeypatch.setattr(module, "_open_issues", lambda repository, token: issues)
    monkeypatch.setattr(module, "_ensure_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "RUNTIME", tmp_path)
    monkeypatch.setattr(module, "EVIDENCE_PATH", tmp_path / "exhausted_issue_requeue.json")

    def fake_request(
        repository: str,
        token: str,
        method: str,
        path: str,
        payload: dict | None = None,
    ):
        calls.append((method, path, payload))
        if method == "GET" and path.endswith("/comments?per_page=100"):
            return []
        if method == "PATCH" and path in {"/issues/101", "/issues/102"}:
            return {"state": "open"}
        return {}

    monkeypatch.setattr(module, "_request", fake_request)

    result = module.run("owner/repo", "token", root=tmp_path, limit=2)

    assert [row["issue"] for row in result["agentic_handoffs"]] == [101, 102]
    assert result["awaiting_agentic_handoff"] == [103]
    assert result["released"] == []
    assert result["successor_handoffs"] == []
    assert not any(method == "POST" and path == "/issues" for method, path, _ in calls)
    assert not any(path == "/issues/103" and method == "PATCH" for method, path, _ in calls)

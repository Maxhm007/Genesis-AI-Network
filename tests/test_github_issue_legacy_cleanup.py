from __future__ import annotations

from pathlib import Path

from genesis.github_issue_legacy_cleanup import cleanup_legacy_managed_duplicates


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = {int(issue["number"]): dict(issue) for issue in issues}

    def __call__(self, method: str, path: str, payload: dict | None = None):
        if method == "GET" and path.startswith("/issues?"):
            return [dict(issue) for issue in self.issues.values() if issue.get("state") == "open"]
        if path.startswith("/issues/"):
            number = int(path.rsplit("/", 1)[1])
            issue = self.issues.get(number)
            if issue is None:
                return None
            if method == "PATCH":
                issue.update(payload or {})
                return dict(issue)
            if method == "GET":
                return dict(issue)
        return None


def _issue(number: int, *, marker: str, problem: str, module: str, evidence: str, title: str | None = None, labels=None):
    return {
        "number": number,
        "title": title or f"[Genesis Escalation] {problem}",
        "body": (
            f"<!-- genesis-chatgpt-escalation:{marker} -->\n"
            f"- **Operational issue:** {problem}\n"
            f"- **Module:** `{module}`\n"
            f"- **Evidence:** {evidence}\n"
        ),
        "state": "open",
        "labels": labels or [],
    }


def test_legacy_changed_fingerprint_closes_older_when_explicit_semantics_match(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(5, marker="old-format", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100"),
        _issue(429, marker="new-format", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100"),
    ])

    result = cleanup_legacy_managed_duplicates(tmp_path, requester=github)

    assert github.issues[5]["state"] == "closed"
    assert github.issues[429]["state"] == "open"
    assert result["closed"][0]["github_issue_number"] == 5
    assert "newer_issue=#429" in result["closed"][0]["reason"]


def test_same_title_different_module_does_not_close(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(10, marker="a", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100"),
        _issue(11, marker="b", problem="AI capability below target", module="genesis.other", evidence="AI Capability Score=37/100"),
    ])

    result = cleanup_legacy_managed_duplicates(tmp_path, requester=github)

    assert result["closed"] == []
    assert github.issues[10]["state"] == "open"
    assert github.issues[11]["state"] == "open"


def test_same_problem_and_module_different_evidence_does_not_close(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(20, marker="a", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=20/100"),
        _issue(21, marker="b", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100"),
    ])

    result = cleanup_legacy_managed_duplicates(tmp_path, requester=github)

    assert result["closed"] == []


def test_protected_legacy_record_is_not_closed(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(30, marker="a", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100", labels=[{"name": "genesis-control"}]),
        _issue(31, marker="b", problem="AI capability below target", module="genesis.ai_score", evidence="AI Capability Score=37/100"),
    ])

    result = cleanup_legacy_managed_duplicates(tmp_path, requester=github)

    assert result["closed"] == []
    assert result["skipped_protected"] == [30]

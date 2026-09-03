from __future__ import annotations

from pathlib import Path

from genesis.github_issue_cleanup import cleanup_obsolete_github_issues


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = {int(issue["number"]): dict(issue) for issue in issues}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/issues?"):
            return [dict(issue) for issue in self.issues.values() if issue.get("state") == "open"]
        if path.startswith("/issues/"):
            number = int(path.rsplit("/", 1)[1])
            issue = self.issues.get(number)
            if issue is None:
                return None
            if method == "GET":
                return dict(issue)
            if method == "PATCH":
                issue.update(payload or {})
                return dict(issue)
        return None


def _issue(
    number: int,
    *,
    title: str = "Repair defect",
    body: str = "",
    labels: list[dict] | None = None,
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": "open",
        "labels": labels or [],
    }


def test_explicit_duplicate_label_closes_unlinked_issue(tmp_path: Path) -> None:
    github = FakeGithub([_issue(10, labels=[{"name": "duplicate"}])])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["status"] == "ok"
    assert result["closed"] == [
        {
            "github_issue_number": 10,
            "reason": "explicit_close_label:duplicate",
            "state_reason": "not_planned",
        }
    ]
    assert github.issues[10]["state"] == "closed"


def test_exact_managed_fingerprint_keeps_newest_and_closes_older(tmp_path: Path) -> None:
    marker = "<!-- genesis-ops:abc123 -->"
    github = FakeGithub([
        _issue(50, title="[Genesis Ops] AI capability below target", body=marker),
        _issue(428, title="[Genesis Ops] AI capability below target", body=marker),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert github.issues[50]["state"] == "closed"
    assert github.issues[428]["state"] == "open"
    assert result["kept_current"] == [
        {"github_issue_number": 428, "managed_kind": "genesis-ops", "fingerprint": "abc123"}
    ]
    assert result["closed"][0]["github_issue_number"] == 50
    assert "newer_issue=#428" in result["closed"][0]["reason"]


def test_ops_and_escalation_with_same_fingerprint_are_separate_kinds(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(50, body="<!-- genesis-ops:same -->"),
        _issue(51, body="<!-- genesis-chatgpt-escalation:same -->"),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert github.issues[50]["state"] == "open"
    assert github.issues[51]["state"] == "open"


def test_protected_duplicate_is_never_closed(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(
            4,
            title="Genesis Control: permanent channel",
            labels=[{"name": "duplicate"}, {"name": "genesis-control"}],
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["skipped_protected"] == [4]
    assert result["closed"] == []
    assert github.issues[4]["state"] == "open"


def test_same_title_without_exact_marker_is_not_cleanup_evidence(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(100, title="Repeated repair title"),
        _issue(101, title="Repeated repair title"),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert github.issues[100]["state"] == "open"
    assert github.issues[101]["state"] == "open"


def test_different_fingerprints_stay_open_even_with_same_managed_title(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(
            5,
            title="[Genesis Escalation] AI capability below target",
            body="<!-- genesis-chatgpt-escalation:old -->",
        ),
        _issue(
            429,
            title="[Genesis Escalation] AI capability below target",
            body="<!-- genesis-chatgpt-escalation:new -->",
        ),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert github.issues[5]["state"] == "open"
    assert github.issues[429]["state"] == "open"

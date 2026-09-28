from genesis.architecture_extensions.pull_request_maintenance import (
    classify_pull_request,
    maintain_open_pull_requests,
)


def _pr(number=10, **overrides):
    row = {
        "number": number,
        "title": "Repair",
        "body": "Fixes #5",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": "abc"},
    }
    row.update(overrides)
    return row


def test_merge_ready_requires_green_checks_and_approval():
    result = classify_pull_request(
        _pr(),
        checks=[{"conclusion": "success"}],
        reviews=[{"user": {"login": "reviewer"}, "state": "APPROVED"}],
    )
    assert result.classification == "merge-ready"
    assert result.linked_issues == (5,)


def test_failed_checks_are_blocked_even_when_mergeable():
    result = classify_pull_request(
        _pr(),
        checks=[{"conclusion": "failure"}],
        reviews=[{"user": {"login": "reviewer"}, "state": "APPROVED"}],
    )
    assert result.classification == "blocked"
    assert "required_validation_not_green" in result.reasons


def test_conflicted_pr_needs_refresh():
    result = classify_pull_request(_pr(mergeable=False, mergeable_state="dirty"))
    assert result.classification == "needs-refresh"


def test_draft_pr_needs_review():
    result = classify_pull_request(_pr(draft=True))
    assert result.classification == "needs-review"


def test_old_pr_is_not_superseded_without_evidence():
    row = _pr(created_at="2020-01-01T00:00:00Z")
    result = classify_pull_request(row, checks=[], reviews=[])
    assert result.classification == "blocked"


def test_explicit_superseded_pr_is_classified_without_age_rule():
    row = _pr(body="Fixes #5\nSuperseded by the implementation on main.")
    result = classify_pull_request(row)
    assert result.classification == "superseded"


class FakeGithub:
    def __init__(self, pr):
        self.pr = dict(pr)
        self.issue = {"number": 5, "state": "open", "labels": []}
        self.calls = []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pulls?"):
            return [dict(self.pr)]
        if method == "GET" and path.startswith("/commits/"):
            return {"check_runs": [{"conclusion": "success"}]}
        if method == "GET" and path.endswith("/reviews?per_page=100"):
            return [{"user": {"login": "reviewer"}, "state": "APPROVED"}]
        if method == "PUT" and path.endswith("/merge"):
            return {"merged": True}
        if method == "POST" and path.endswith("/comments"):
            return {"id": 1}
        if method == "PATCH" and path.startswith("/pulls/"):
            self.pr["state"] = payload["state"]
            return dict(self.pr)
        if method == "GET" and path == "/issues/5":
            return dict(self.issue)
        if method == "PATCH" and path == "/issues/5":
            self.issue.update(payload)
            return dict(self.issue)
        return None


def test_maintenance_merges_only_verified_merge_ready_pr():
    github = FakeGithub(_pr())
    result = maintain_open_pull_requests(github)
    assert result["merged"] == [10]
    assert any(method == "PUT" and path == "/pulls/10/merge" for method, path, _ in github.calls)


def test_superseded_close_requeues_linked_open_issue():
    github = FakeGithub(_pr(body="Fixes #5\nObsolete; superseded by current main."))
    result = maintain_open_pull_requests(github)
    assert result["closed"] == [10]
    assert result["requeued"] == [5]
    assert "genesis-autonomous" in github.issue["labels"]
    assert not any(method == "PUT" and path.endswith("/merge") for method, path, _ in github.calls)

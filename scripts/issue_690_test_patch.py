from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests" / "test_github_issue_cleanup.py"
text = path.read_text(encoding="utf-8")

old_fake = '''        if method == "GET" and path.startswith("/issues?"):\n            return [dict(issue) for issue in self.issues.values() if issue.get("state") == "open"]\n        if path.startswith("/issues/"):\n            number = int(path.rsplit("/", 1)[1])\n'''
new_fake = '''        if method == "GET" and path.startswith("/issues?"):\n            return [dict(issue) for issue in self.issues.values() if issue.get("state") == "open"]\n        if method == "POST" and path.startswith("/issues/") and path.endswith("/comments"):\n            return {"id": len(self.calls), "body": str((payload or {}).get("body") or "")}\n        if path.startswith("/issues/"):\n            number = int(path.rsplit("/", 1)[1])\n'''
if old_fake not in text:
    raise SystemExit("FakeGithub anchor missing")
text = text.replace(old_fake, new_fake, 1)

old_test = '''def test_ops_and_escalation_with_same_fingerprint_are_separate_kinds(tmp_path: Path) -> None:\n    github = FakeGithub([\n        _issue(50, body="<!-- genesis-ops:same -->"),\n        _issue(51, body="<!-- genesis-chatgpt-escalation:same -->"),\n    ])\n\n    result = cleanup_obsolete_github_issues(tmp_path, requester=github)\n\n    assert result["closed"] == []\n    assert github.issues[50]["state"] == "open"\n    assert github.issues[51]["state"] == "open"\n'''
new_test = '''def test_ops_and_escalation_with_same_fingerprint_keep_one_canonical_record(tmp_path: Path) -> None:\n    github = FakeGithub([\n        _issue(50, body="<!-- genesis-ops:same -->"),\n        _issue(51, body="<!-- genesis-chatgpt-escalation:same -->"),\n    ])\n\n    result = cleanup_obsolete_github_issues(tmp_path, requester=github)\n\n    assert github.issues[50]["state"] == "open"\n    assert github.issues[51]["state"] == "closed"\n    assert result["closed"][0]["github_issue_number"] == 51\n    assert "canonical_issue=#50" in result["closed"][0]["reason"]\n'''
if old_test not in text:
    raise SystemExit("legacy ops/escalation test anchor missing")
text = text.replace(old_test, new_test, 1)

path.write_text(text, encoding="utf-8")
print("Issue #690 test harness aligned")

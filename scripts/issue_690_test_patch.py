from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "tests" / "test_github_issue_cleanup.py"
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

pagination = root / "tests" / "test_oldest_issue_solver_pagination.py"
ptext = pagination.read_text(encoding="utf-8")
old_boundary = '''def test_sequential_controller_preserves_skip_boundaries():\n    text = CONTROLLER.read_text(encoding="utf-8")\n\n    assert "genesis-solver-exhausted" in text\n    assert "lower_title.startswith(('genesis chat:', '[genesis hourly report]', '[genesis gene chat]'))" in text\n    assert "'persistent github-native reporting channel' in lower_body" in text\n    assert "protected_targets" in text\n    assert "requires_measurement" in text\n    assert "external-authority / independent-secret provisioning blocker" in text\n'''
new_boundary = '''def test_sequential_controller_preserves_safety_boundaries_without_skipping_work_classes():\n    text = CONTROLLER.read_text(encoding="utf-8")\n\n    assert "genesis-solver-exhausted" in text\n    assert "genesis-deferred" in text\n    assert "lower_title.startswith(('genesis chat:', '[genesis hourly report]', '[genesis gene chat]'))" in text\n    assert "'persistent github-native reporting channel' in lower_body" in text\n    assert "protected_targets" in text\n    assert "python -m genesis.github_issue_cleanup" in text\n    assert "requires_measurement" not in text\n    assert "external-authority / independent-secret provisioning blocker" not in text\n'''
if old_boundary not in ptext:
    raise SystemExit("legacy controller skip-boundary test anchor missing")
pagination.write_text(ptext.replace(old_boundary, new_boundary, 1), encoding="utf-8")

print("Issue #690 test harness aligned")

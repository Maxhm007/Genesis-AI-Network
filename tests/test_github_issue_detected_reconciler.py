from __future__ import annotations

from pathlib import Path

from genesis.github_issue_detected_reconciler import reconcile_satisfied_detected_issues


class FakeGithub:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = {int(issue["number"]): dict(issue) for issue in issues}
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.startswith("/issues?"):
            return [dict(issue) for issue in self.issues.values() if issue.get("state", "open") == "open"]
        if not path.startswith("/issues/"):
            return None

        parts = path.split("/")
        number = int(parts[2])
        issue = self.issues.get(number)
        if issue is None:
            return None
        if method == "POST" and path.endswith("/comments"):
            return {"id": 1, "body": str((payload or {}).get("body") or "")}
        if method == "POST" and path.endswith("/labels"):
            current = [dict(label) for label in issue.get("labels") or []]
            names = {str(label.get("name") or "") for label in current}
            for name in (payload or {}).get("labels") or []:
                if name not in names:
                    current.append({"name": name})
            issue["labels"] = current
            return current
        if method == "DELETE" and "/labels/" in path:
            name = path.rsplit("/", 1)[1]
            issue["labels"] = [label for label in issue.get("labels") or [] if label.get("name") != name]
            return {}
        if method == "PATCH" and path == f"/issues/{number}":
            issue.update(payload or {})
            return dict(issue)
        return None


def _write_target(root: Path, *, bad: bool = False, with_test: bool = True) -> None:
    target = root / "genesis" / "modules" / "versioning.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    operator = ">" if bad else "<"
    target.write_text(
        "class ModuleVersionManager:\n"
        "    @staticmethod\n"
        "    def should_rollback(before_percent, after_percent, regression_tolerance=0.0):\n"
        f"        return after_percent {operator} before_percent - regression_tolerance\n",
        encoding="utf-8",
    )
    if with_test:
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "test_versioning.py").write_text(
            "def test_regression_triggers_rollback_decision():\n"
            "    assert True\n",
            encoding="utf-8",
        )


def _issue(*, author: str = "github-actions[bot]", labels: list[dict] | None = None) -> dict:
    return {
        "number": 560,
        "title": "[Genesis Detected] Fix reversed rollback comparison",
        "state": "open",
        "user": {"login": author},
        "labels": labels or [],
        "body": (
            "Genesis autonomously detected a real logic regression.\n\n"
            "- **Target:** `genesis/modules/versioning.py`\n"
            "- **Observed defect:** `ModuleVersionManager.should_rollback()` currently uses `after_percent > before_percent - regression_tolerance`.\n"
            "- **Expected behavior:** rollback only when the post-change score is lower.\n"
            "- **Verification:** compile the target and pass the full repository test suite before closing.\n"
        ),
    }


def test_already_satisfied_bot_detected_regression_is_verified_and_closed(tmp_path: Path) -> None:
    _write_target(tmp_path)
    github = FakeGithub([_issue()])
    commands: list[list[str]] = []

    def runner(args: list[str], root: Path) -> bool:
        assert root == tmp_path.resolve()
        commands.append(list(args))
        return True

    result = reconcile_satisfied_detected_issues(
        tmp_path,
        requester=github,
        runner=runner,
        prepare_dependencies=lambda root: True,
    )

    assert result["closed"] == [560]
    assert github.issues[560]["state"] == "closed"
    assert github.issues[560]["state_reason"] == "completed"
    assert {label["name"] for label in github.issues[560]["labels"]} == {"genesis-verified"}
    assert commands == [["-q", "tests/test_versioning.py"], ["-q"]]
    assert any(method == "POST" and path.endswith("/comments") for method, path, _ in github.calls)


def test_detected_regression_stays_open_while_reported_bad_fragment_is_present(tmp_path: Path) -> None:
    _write_target(tmp_path, bad=True)
    github = FakeGithub([_issue()])
    commands: list[list[str]] = []

    result = reconcile_satisfied_detected_issues(
        tmp_path,
        requester=github,
        runner=lambda args, root: commands.append(list(args)) or True,
        prepare_dependencies=lambda root: True,
    )

    assert result["closed"] == []
    assert github.issues[560]["state"] == "open"
    assert commands == []
    assert result["skipped"][0]["reason"] == "reported_bad_fragment_still_present"


def test_user_authored_detected_title_cannot_use_verification_shortcut(tmp_path: Path) -> None:
    _write_target(tmp_path)
    github = FakeGithub([_issue(author="Maxhm007")])

    result = reconcile_satisfied_detected_issues(
        tmp_path,
        requester=github,
        runner=lambda args, root: True,
        prepare_dependencies=lambda root: True,
    )

    assert result["candidate"] is None
    assert result["closed"] == []
    assert github.issues[560]["state"] == "open"
    assert not any(method == "PATCH" for method, _, _ in github.calls)


def test_active_detected_issue_is_not_reconciled_out_from_under_worker(tmp_path: Path) -> None:
    _write_target(tmp_path)
    github = FakeGithub([_issue(labels=[{"name": "genesis-repair-in-progress"}])])

    result = reconcile_satisfied_detected_issues(
        tmp_path,
        requester=github,
        runner=lambda args, root: True,
        prepare_dependencies=lambda root: True,
    )

    assert result["closed"] == []
    assert result["skipped"][0]["reason"] == "protected_or_active"
    assert github.issues[560]["state"] == "open"


def test_missing_focused_test_fails_closed(tmp_path: Path) -> None:
    _write_target(tmp_path, with_test=False)
    github = FakeGithub([_issue()])

    result = reconcile_satisfied_detected_issues(
        tmp_path,
        requester=github,
        runner=lambda args, root: True,
        prepare_dependencies=lambda root: True,
    )

    assert result["closed"] == []
    assert result["skipped"][0]["reason"] == "focused_test_missing"
    assert github.issues[560]["state"] == "open"

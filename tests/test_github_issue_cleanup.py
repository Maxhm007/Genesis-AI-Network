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
        if method == "POST" and path.startswith("/issues/") and path.endswith("/comments"):
            return {"id": len(self.calls), "body": str((payload or {}).get("body") or "")}
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


def test_ops_and_escalation_with_same_fingerprint_keep_one_canonical_record(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(50, body="<!-- genesis-ops:same -->"),
        _issue(51, body="<!-- genesis-chatgpt-escalation:same -->"),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert github.issues[50]["state"] == "open"
    assert github.issues[51]["state"] == "closed"
    assert result["closed"][0]["github_issue_number"] == 51
    assert "canonical_issue=#50" in result["closed"][0]["reason"]


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


def test_benchmark_runner_task_gets_deterministic_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "benchmark_execution.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            350,
            title="[Genesis Task] benchmark runner integration",
            body=(
                "- **Task type:** `benchmark_runner_integration`\n"
                "Make the comparable benchmark runner executable."
            ),
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"] == [
        {
            "github_issue_number": 350,
            "target": "genesis/benchmark_execution.py",
            "reason": "task_type_map:benchmark_runner_integration",
        }
    ]
    assert "- **Target:** `genesis/benchmark_execution.py`" in github.issues[350]["body"]


def test_single_evidenced_python_path_is_routed_for_ordinary_task(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            351,
            title="[Genesis Task] repair evidenced behavior",
            body="Current failure evidence points to `genesis/example.py` only.",
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"][0]["target"] == "genesis/example.py"
    assert result["routed"][0]["reason"] == "single_evidenced_python_path"


def test_ambiguous_or_protected_python_paths_are_not_routed(tmp_path: Path) -> None:
    genesis = tmp_path / "genesis"
    genesis.mkdir(parents=True)
    (genesis / "one.py").write_text("VALUE = 1\n", encoding="utf-8")
    (genesis / "two.py").write_text("VALUE = 2\n", encoding="utf-8")
    (genesis / "security.py").write_text("VALUE = 3\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            352,
            title="[Genesis Task] ambiguous repair",
            body="Evidence mentions genesis/one.py and genesis/two.py.",
        ),
        _issue(
            353,
            title="[Genesis Task] protected repair",
            body="Evidence mentions only genesis/security.py.",
        ),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"] == []
    assert "**Target:**" not in github.issues[352]["body"]
    assert "**Target:**" not in github.issues[353]["body"]


def test_measurement_task_is_not_forced_into_generic_repair(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            354,
            title="[Genesis Task] measured capability growth",
            body=(
                "Evidence mentions genesis/example.py.\n"
                "The same comparable benchmark must show measured score improves."
            ),
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"] == []
    assert "**Target:**" not in github.issues[354]["body"]


def test_repair_issue_with_python_path_is_not_inferred_into_single_file_lane(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            355,
            title="[Genesis Repair] control-plane repair",
            body="One part mentions genesis/example.py but the repair may require other boundaries.",
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"] == []
    assert "**Target:**" not in github.issues[355]["body"]

def test_dotted_suffix_after_python_path_is_not_treated_as_safe_target(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            356,
            title="[Genesis Task] backup artifact reference",
            body="Evidence mentions genesis/example.py.bak only.",
        )
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["routed"] == []
    assert "**Target:**" not in github.issues[356]["body"]

def test_frontier_measurement_routes_to_benchmark_execution(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "benchmark_execution.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            375,
            title="[Genesis Task] frontier benchmark measurement",
            body="- **Task type:** `frontier_benchmark_measurement`\nRecord a real comparable measurement.",
        )
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert result["routed"][0]["target"] == "genesis/benchmark_execution.py"


def test_self_improvement_task_type_can_route_without_genesis_task_title(tmp_path: Path) -> None:
    target = tmp_path / "genesis" / "pulse.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    github = FakeGithub([
        _issue(
            341,
            title="[Genesis Self Improvement] gene velocity improvement",
            body="- **Task type:** `gene_velocity_improvement`\nReduce validated development latency.",
        )
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert result["routed"][0]["target"] == "genesis/pulse.py"


def test_external_authority_blocker_is_terminally_closed(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(
            55,
            body="Treat this as an external-authority / independent-secret provisioning blocker, not a retryable code defect.",
        )
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert github.issues[55]["state"] == "closed"
    assert result["closed"][0]["reason"] == "external_authority_dependency_documented"


def test_ops_record_supersedes_same_fingerprint_escalation(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(428, title="[Genesis Ops] AI capability below target", body="<!-- genesis-ops:same -->"),
        _issue(429, title="[Genesis Escalation] AI capability below target", body="<!-- genesis-chatgpt-escalation:same -->"),
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert github.issues[428]["state"] == "open"
    assert github.issues[429]["state"] == "closed"
    assert any(row["github_issue_number"] == 429 for row in result["closed"])



def test_exact_duplicate_actionable_issues_keep_oldest_canonical(tmp_path: Path) -> None:
    body = "- **Target:** `genesis/example.py`\nFix the exact same defect."
    github = FakeGithub([
        _issue(560, title="[Genesis Detected] Exact defect", body=body),
        _issue(562, title="[Genesis Detected] Exact defect", body=body),
        _issue(563, title="[Genesis Detected] Exact defect", body=body),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert github.issues[560]["state"] == "open"
    assert github.issues[562]["state"] == "closed"
    assert github.issues[563]["state"] == "closed"
    assert [row["github_issue_number"] for row in result["closed"]] == [562, 563]
    assert any(row.get("managed_kind") == "exact_duplicate_canonical" and row["github_issue_number"] == 560 for row in result["kept_current"])


def test_same_title_with_different_full_body_is_not_exact_duplicate(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(570, title="[Genesis Detected] Same title", body="- **Target:** `genesis/example.py`\nDefect A"),
        _issue(571, title="[Genesis Detected] Same title", body="- **Target:** `genesis/example.py`\nDefect B"),
    ])

    result = cleanup_obsolete_github_issues(tmp_path, requester=github)

    assert result["closed"] == []
    assert github.issues[570]["state"] == "open"
    assert github.issues[571]["state"] == "open"

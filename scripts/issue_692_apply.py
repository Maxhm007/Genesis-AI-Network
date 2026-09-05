from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing {label} anchor")
    return text.replace(old, new, 1)


# 1) Conservative exact duplicate cleanup.
cleanup_path = ROOT / "genesis" / "github_issue_cleanup.py"
cleanup = cleanup_path.read_text(encoding="utf-8")
if "def _exact_duplicate_key" not in cleanup:
    anchor = '''def _managed_key(issue: dict) -> tuple[str, str] | None:\n    body = str(issue.get("body") or "")\n    match = MANAGED_MARKER_RE.search(body)\n    if not match:\n        return None\n    return match.group(1).lower(), match.group(2).lower()\n\n\n'''
    addition = anchor + '''def _normalize_exact_text(value: object) -> str:\n    text = str(value or "").replace("\\r\\n", "\\n").replace("\\r", "\\n").strip()\n    return "\\n".join(line.rstrip() for line in text.split("\\n"))\n\n\ndef _exact_duplicate_key(issue: dict) -> tuple[str, str] | None:\n    """Return a key only for exact actionable records after newline normalization."""\n    if _protected_issue(issue) or _managed_key(issue) is not None:\n        return None\n    title = " ".join(str(issue.get("title") or "").split()).lower()\n    body = _normalize_exact_text(issue.get("body"))\n    if not title or not body:\n        return None\n    if title.startswith(("genesis chat:", "[genesis hourly report]", "[genesis gene chat]")):\n        return None\n    return title, body\n\n\n'''
    cleanup = require_replace(cleanup, anchor, addition, "duplicate helper")
if "exact_duplicate_of:#" not in cleanup:
    anchor = "    groups: dict[tuple[str, str], list[dict]] = {}\n"
    block = '''    exact_groups: dict[tuple[str, str], list[dict]] = {}\n    for issue in remaining:\n        key = _exact_duplicate_key(issue)\n        if key is not None:\n            exact_groups.setdefault(key, []).append(issue)\n\n    for rows in exact_groups.values():\n        if len(rows) < 2:\n            continue\n        canonical = min(rows, key=_issue_number)\n        canonical_number = _issue_number(canonical)\n        result["kept_current"].append(\n            {"github_issue_number": canonical_number, "managed_kind": "exact_duplicate_canonical"}\n        )\n        for issue in sorted(rows, key=_issue_number):\n            number = _issue_number(issue)\n            if number == canonical_number:\n                continue\n            closed = _close_issue(\n                requester,\n                issue,\n                reason=f"exact_duplicate_of:#{canonical_number}",\n            )\n            if closed is None:\n                result["blocked"].append(\n                    {"github_issue_number": number, "reason": "exact_duplicate_close_failed"}\n                )\n            else:\n                result["closed"].append(closed)\n\n'''
    cleanup = require_replace(cleanup, anchor, block + anchor, "duplicate grouping")
cleanup_path.write_text(cleanup, encoding="utf-8")

# 2) A solver policy change is a new repair-engine generation; measurements/Model Lab may retry.
requeue_path = ROOT / "scripts" / "requeue_exhausted_issues.py"
requeue = requeue_path.read_text(encoding="utf-8")
old_engine = '''ENGINE_PATHS = (\n    "genesis/coding.py",\n    "genesis/compact_edit_budget.py",\n    ".github/workflows/genesis-bounded-repair-worker.yml",\n    "scripts/github_issue_autorepair.py",\n    "genesis/learned_capabilities.py",\n)\n'''
new_engine = '''ENGINE_PATHS = (\n    "genesis/coding.py",\n    "genesis/compact_edit_budget.py",\n    ".github/workflows/genesis-bounded-repair-worker.yml",\n    ".github/workflows/genesis-sequential-issue-controller.yml",\n    "scripts/github_issue_autorepair.py",\n    "scripts/requeue_exhausted_issues.py",\n    "genesis/github_issue_cleanup.py",\n    "genesis/learned_capabilities.py",\n)\n'''
if '"genesis/github_issue_cleanup.py"' not in requeue.split("ACTIVE_LABELS", 1)[0]:
    requeue = require_replace(requeue, old_engine, new_engine, "engine generation")
requeue = requeue.replace('    if lower_title.startswith("genesis model lab:"):\n        return False, "umbrella_state"\n', '')
requeue = requeue.replace('    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):\n        return False, "measurement_lane"\n', '')
requeue_path.write_text(requeue, encoding="utf-8")

# 3) Bounded worker must terminally close exhausted work instead of leaving it open forever.
worker_path = ROOT / ".github" / "workflows" / "genesis-bounded-repair-worker.yml"
worker = worker_path.read_text(encoding="utf-8")
if "terminal_deferred=true" not in worker:
    old = '''          if [[ "$evidence_status" == "blocked" || "$solver_attempt" -ge 3 ]]; then\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-blocked >/dev/null 2>&1 || true\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-solver-exhausted >/dev/null 2>&1 || true\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --remove-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='bounded attempts exhausted; queue will move on'\n          else\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='issue remains open for the bounded retry policy'\n          fi\n\n          gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" \\\n            --body "Genesis bounded repair did not promote a verified change in worker run ${GITHUB_RUN_ID} (repair status: \\`${evidence_status:-worker_failed_before_evidence}\\`, solver attempt: ${solver_attempt}/3). The repair reservation was released safely; ${retry_state}."\n'''
    new = '''          if [[ "$evidence_status" == "blocked" || "$solver_attempt" -ge 3 ]]; then\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-blocked >/dev/null 2>&1 || true\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-solver-exhausted >/dev/null 2>&1 || true\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-deferred >/dev/null 2>&1 || true\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --remove-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='terminally deferred under the current repair-engine generation; a changed repair engine may reopen it automatically'\n            terminal_deferred=true\n          else\n            gh issue edit "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" --add-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='issue remains open for the bounded retry policy'\n            terminal_deferred=false\n          fi\n\n          gh issue comment "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY" \\\n            --body "Genesis bounded repair did not promote a verified change in worker run ${GITHUB_RUN_ID} (repair status: \\`${evidence_status:-worker_failed_before_evidence}\\`, solver attempt: ${solver_attempt}/3). The repair reservation was released safely; ${retry_state}."\n          if [[ "$terminal_deferred" == "true" ]]; then\n            gh api "repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}" --method PATCH -f state=closed -f state_reason=not_planned >/dev/null\n          fi\n'''
    worker = require_replace(worker, old, new, "bounded worker terminal block")
worker_path.write_text(worker, encoding="utf-8")

# 4) Requeue workflow follows the authoritative controller and all engine-policy paths.
workflow_path = ROOT / ".github" / "workflows" / "genesis-exhausted-issue-requeue.yml"
workflow = workflow_path.read_text(encoding="utf-8")
if "genesis/github_issue_cleanup.py" not in workflow:
    workflow = require_replace(
        workflow,
        '      - scripts/github_issue_autorepair.py\n      - scripts/requeue_exhausted_issues.py\n      - .github/workflows/genesis-exhausted-issue-requeue.yml\n',
        '      - scripts/github_issue_autorepair.py\n      - scripts/requeue_exhausted_issues.py\n      - genesis/github_issue_cleanup.py\n      - .github/workflows/genesis-bounded-repair-worker.yml\n      - .github/workflows/genesis-sequential-issue-controller.yml\n      - .github/workflows/genesis-exhausted-issue-requeue.yml\n',
        "requeue triggers",
    )
workflow = workflow.replace("--workflow genesis-oldest-issue-solver.yml", "--workflow genesis-sequential-issue-controller.yml")
workflow = workflow.replace("gh workflow run genesis-oldest-issue-solver.yml", "gh workflow run genesis-sequential-issue-controller.yml")
workflow = workflow.replace("Woke the normal oldest Issue solver.", "Woke the authoritative Sequential Issue Controller.")
workflow = workflow.replace("Oldest Issue solver is already active or queued; no duplicate wake dispatched.", "Sequential Issue Controller is already active or queued; no duplicate wake dispatched.")
workflow_path.write_text(workflow, encoding="utf-8")

# 5) Focused regressions.
cleanup_tests = ROOT / "tests" / "test_github_issue_cleanup.py"
ctext = cleanup_tests.read_text(encoding="utf-8")
if "test_exact_duplicate_actionable_issues_keep_oldest_only" not in ctext:
    ctext += r'''


def test_exact_duplicate_actionable_issues_keep_oldest_only(tmp_path: Path) -> None:
    body = "- **Target:** `genesis/example.py`\n\nSame exact defect."
    github = FakeGithub([
        _issue(560, title="[Genesis Detected] Fix defect", body=body),
        _issue(562, title="[Genesis Detected] Fix defect", body=body),
        _issue(563, title="[Genesis Detected] Fix defect", body=body),
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert github.issues[560]["state"] == "open"
    assert github.issues[562]["state"] == "closed"
    assert github.issues[563]["state"] == "closed"
    assert {row["github_issue_number"] for row in result["closed"]} == {562, 563}


def test_same_title_with_different_body_is_not_exact_duplicate(tmp_path: Path) -> None:
    github = FakeGithub([
        _issue(1, title="[Genesis Detected] Fix defect", body="first"),
        _issue(2, title="[Genesis Detected] Fix defect", body="second"),
    ])
    result = cleanup_obsolete_github_issues(tmp_path, requester=github)
    assert result["closed"] == []
    assert github.issues[1]["state"] == "open"
    assert github.issues[2]["state"] == "open"
'''
cleanup_tests.write_text(ctext, encoding="utf-8")

requeue_tests = ROOT / "tests" / "test_requeue_exhausted_issues.py"
rtext = requeue_tests.read_text(encoding="utf-8")
if 'assert ".github/workflows/genesis-sequential-issue-controller.yml" in ENGINE_PATHS' not in rtext:
    rtext = rtext.replace(
        '    assert ".github/workflows/genesis-bounded-repair-worker.yml" in ENGINE_PATHS\n',
        '    assert ".github/workflows/genesis-bounded-repair-worker.yml" in ENGINE_PATHS\n'
        '    assert ".github/workflows/genesis-sequential-issue-controller.yml" in ENGINE_PATHS\n'
        '    assert "genesis/github_issue_cleanup.py" in ENGINE_PATHS\n'
        '    assert "scripts/requeue_exhausted_issues.py" in ENGINE_PATHS\n',
    )
rtext = rtext.replace("def test_measurement_and_protected_issues_are_not_requeued(tmp_path: Path):", "def test_measurement_is_requeueable_but_protected_target_is_not(tmp_path: Path):")
rtext = rtext.replace(
    '    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (False, "measurement_lane")',
    '    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (True, "genesis/example.py")',
)
requeue_tests.write_text(rtext, encoding="utf-8")

policy = ROOT / "tests" / "test_solver_terminal_policy.py"
policy.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_bounded_worker_terminally_defers_exhausted_issue():\n    text = (ROOT / ".github/workflows/genesis-bounded-repair-worker.yml").read_text(encoding="utf-8")\n    assert "--add-label genesis-deferred" in text\n    assert "-f state=closed -f state_reason=not_planned" in text\n    assert "changed repair engine may reopen it automatically" in text\n\ndef test_requeue_wakes_authoritative_sequential_controller():\n    text = (ROOT / ".github/workflows/genesis-exhausted-issue-requeue.yml").read_text(encoding="utf-8")\n    assert "--workflow genesis-sequential-issue-controller.yml" in text\n    assert "gh workflow run genesis-sequential-issue-controller.yml" in text\n    assert "genesis-oldest-issue-solver.yml" not in text\n''', encoding="utf-8")

print("Issue #692 patch applied")

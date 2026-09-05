from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"missing current-state anchor for {label}")
    return text.replace(old, new, 1)


def patch_cleanup() -> None:
    path = ROOT / "genesis/github_issue_cleanup.py"
    text = path.read_text(encoding="utf-8")
    marker = """def _managed_key(issue: dict) -> tuple[str, str] | None:\n    body = str(issue.get(\"body\") or \"\")\n    match = MANAGED_MARKER_RE.search(body)\n    if not match:\n        return None\n    return match.group(1).lower(), match.group(2).lower()\n\n\n"""
    addition = marker + """def _normalize_exact_text(value: object) -> str:\n    text = str(value or \"\").replace(\"\\r\\n\", \"\\n\").replace(\"\\r\", \"\\n\").strip()\n    return \"\\n\".join(line.rstrip() for line in text.split(\"\\n\"))\n\n\ndef _exact_duplicate_key(issue: dict) -> tuple[str, str] | None:\n    \"\"\"Return a key only for exact actionable records after harmless newline cleanup.\"\"\"\n    if _protected_issue(issue) or _managed_key(issue) is not None:\n        return None\n    title = \" \".join(str(issue.get(\"title\") or \"\").split()).lower()\n    body = _normalize_exact_text(issue.get(\"body\"))\n    if not title or not body:\n        return None\n    if title.startswith((\"genesis chat:\", \"[genesis hourly report]\", \"[genesis gene chat]\")):\n        return None\n    return title, body\n\n\n"""
    text = replace_once(text, marker, addition, "exact duplicate key")

    old = """    groups: dict[tuple[str, str], list[dict]] = {}\n    for issue in remaining:\n        key = _managed_key(issue)\n"""
    new = """    exact_groups: dict[tuple[str, str], list[dict]] = {}\n    for issue in remaining:\n        key = _exact_duplicate_key(issue)\n        if key is not None:\n            exact_groups.setdefault(key, []).append(issue)\n\n    for rows in exact_groups.values():\n        if len(rows) < 2:\n            continue\n        canonical = min(rows, key=_issue_number)\n        canonical_number = _issue_number(canonical)\n        result[\"kept_current\"].append(\n            {\"github_issue_number\": canonical_number, \"managed_kind\": \"exact_duplicate_canonical\"}\n        )\n        for issue in sorted(rows, key=_issue_number):\n            number = _issue_number(issue)\n            if number == canonical_number:\n                continue\n            closed = _close_issue(\n                requester,\n                issue,\n                reason=f\"exact_duplicate_of:#{canonical_number}\",\n            )\n            if closed is None:\n                result[\"blocked\"].append(\n                    {\"github_issue_number\": number, \"reason\": \"exact_duplicate_close_failed\"}\n                )\n            else:\n                result[\"closed\"].append(closed)\n\n    groups: dict[tuple[str, str], list[dict]] = {}\n    for issue in remaining:\n        key = _managed_key(issue)\n"""
    text = replace_once(text, old, new, "exact duplicate collapse")
    path.write_text(text, encoding="utf-8")


def patch_requeue_script() -> None:
    path = ROOT / "scripts/requeue_exhausted_issues.py"
    text = path.read_text(encoding="utf-8")
    old = """ENGINE_PATHS = (\n    \"genesis/coding.py\",\n    \"genesis/compact_edit_budget.py\",\n    \".github/workflows/genesis-bounded-repair-worker.yml\",\n    \"scripts/github_issue_autorepair.py\",\n    \"genesis/learned_capabilities.py\",\n)\n"""
    new = """ENGINE_PATHS = (\n    \"genesis/coding.py\",\n    \"genesis/compact_edit_budget.py\",\n    \".github/workflows/genesis-bounded-repair-worker.yml\",\n    \".github/workflows/genesis-sequential-issue-controller.yml\",\n    \"scripts/github_issue_autorepair.py\",\n    \"scripts/requeue_exhausted_issues.py\",\n    \"genesis/github_issue_cleanup.py\",\n    \"genesis/learned_capabilities.py\",\n)\n"""
    text = replace_once(text, old, new, "repair engine generation inputs")
    text = text.replace('    if lower_title.startswith("genesis model lab:"):\n        return False, "umbrella_state"\n', "")
    text = text.replace('    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):\n        return False, "measurement_lane"\n', "")
    path.write_text(text, encoding="utf-8")


def patch_worker() -> None:
    path = ROOT / ".github/workflows/genesis-bounded-repair-worker.yml"
    text = path.read_text(encoding="utf-8")
    old = """          if [[ \"$evidence_status\" == \"blocked\" || \"$solver_attempt\" -ge 3 ]]; then\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-blocked >/dev/null 2>&1 || true\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-solver-exhausted >/dev/null 2>&1 || true\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --remove-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='bounded attempts exhausted; queue will move on'\n          else\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='issue remains open for the bounded retry policy'\n          fi\n\n          gh issue comment \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" \\\n            --body \"Genesis bounded repair did not promote a verified change in worker run ${GITHUB_RUN_ID} (repair status: \\`${evidence_status:-worker_failed_before_evidence}\\`, solver attempt: ${solver_attempt}/3). The repair reservation was released safely; ${retry_state}.\"\n"""
    new = """          terminal_deferred=false\n          if [[ \"$evidence_status\" == \"blocked\" || \"$solver_attempt\" -ge 3 ]]; then\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-blocked >/dev/null 2>&1 || true\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-solver-exhausted >/dev/null 2>&1 || true\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-deferred >/dev/null 2>&1 || true\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --remove-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='terminally deferred under the current repair-engine generation; a changed repair engine may reopen it automatically'\n            terminal_deferred=true\n          else\n            gh issue edit \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" --add-label genesis-autonomous >/dev/null 2>&1 || true\n            retry_state='issue remains open for the bounded retry policy'\n          fi\n\n          gh issue comment \"$ISSUE_NUMBER\" --repo \"$GITHUB_REPOSITORY\" \\\n            --body \"Genesis bounded repair did not promote a verified change in worker run ${GITHUB_RUN_ID} (repair status: \\`${evidence_status:-worker_failed_before_evidence}\\`, solver attempt: ${solver_attempt}/3). The repair reservation was released safely; ${retry_state}.\"\n\n          if [[ \"$terminal_deferred\" == \"true\" ]]; then\n            gh api \"repos/${GITHUB_REPOSITORY}/issues/${ISSUE_NUMBER}\" \\\n              --method PATCH -f state=closed -f state_reason=not_planned >/dev/null\n          fi\n"""
    text = replace_once(text, old, new, "bounded worker terminal defer")
    path.write_text(text, encoding="utf-8")


def patch_requeue_workflow() -> None:
    path = ROOT / ".github/workflows/genesis-exhausted-issue-requeue.yml"
    text = path.read_text(encoding="utf-8")
    old_paths = """      - genesis/coding.py\n      - genesis/learned_capabilities.py\n      - scripts/github_issue_autorepair.py\n      - scripts/requeue_exhausted_issues.py\n      - .github/workflows/genesis-exhausted-issue-requeue.yml\n"""
    new_paths = """      - genesis/coding.py\n      - genesis/learned_capabilities.py\n      - genesis/github_issue_cleanup.py\n      - scripts/github_issue_autorepair.py\n      - scripts/requeue_exhausted_issues.py\n      - .github/workflows/genesis-bounded-repair-worker.yml\n      - .github/workflows/genesis-sequential-issue-controller.yml\n      - .github/workflows/genesis-exhausted-issue-requeue.yml\n"""
    text = replace_once(text, old_paths, new_paths, "requeue push paths")
    old = """      - name: Wake oldest solver only when idle\n        env:\n          GH_TOKEN: ${{ github.token }}\n        shell: bash\n        run: |\n          set -euo pipefail\n          released=$(jq '.released | length' runtime/exhausted_issue_requeue.json)\n          if [ \"$released\" -eq 0 ]; then\n            echo 'No exhausted Issues released.'\n            exit 0\n          fi\n\n          running=$(gh run list --repo \"$GITHUB_REPOSITORY\" --workflow genesis-oldest-issue-solver.yml \\\n            --status in_progress --limit 1 --json databaseId --jq 'length')\n          queued=$(gh run list --repo \"$GITHUB_REPOSITORY\" --workflow genesis-oldest-issue-solver.yml \\\n            --status queued --limit 1 --json databaseId --jq 'length')\n          if [ \"$running\" -eq 0 ] && [ \"$queued\" -eq 0 ]; then\n            gh workflow run genesis-oldest-issue-solver.yml --repo \"$GITHUB_REPOSITORY\" --ref main\n            echo 'Woke the normal oldest Issue solver.'\n          else\n            echo 'Oldest Issue solver is already active or queued; no duplicate wake dispatched.'\n          fi\n"""
    new = """      - name: Wake authoritative Sequential Issue Controller only when idle\n        env:\n          GH_TOKEN: ${{ github.token }}\n        shell: bash\n        run: |\n          set -euo pipefail\n          released=$(jq '.released | length' runtime/exhausted_issue_requeue.json)\n          if [ \"$released\" -eq 0 ]; then\n            echo 'No exhausted Issues released.'\n            exit 0\n          fi\n\n          running=$(gh run list --repo \"$GITHUB_REPOSITORY\" --workflow genesis-sequential-issue-controller.yml \\\n            --status in_progress --limit 1 --json databaseId --jq 'length')\n          queued=$(gh run list --repo \"$GITHUB_REPOSITORY\" --workflow genesis-sequential-issue-controller.yml \\\n            --status queued --limit 1 --json databaseId --jq 'length')\n          if [ \"$running\" -eq 0 ] && [ \"$queued\" -eq 0 ]; then\n            gh workflow run genesis-sequential-issue-controller.yml --repo \"$GITHUB_REPOSITORY\" --ref main\n            echo 'Woke the authoritative Sequential Issue Controller.'\n          else\n            echo 'Sequential Issue Controller is already active or queued; no duplicate wake dispatched.'\n          fi\n"""
    text = replace_once(text, old, new, "authoritative requeue wake")
    path.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    cleanup = ROOT / "tests/test_github_issue_cleanup.py"
    text = cleanup.read_text(encoding="utf-8")
    marker = "def test_exact_duplicate_actionable_issues_keep_oldest_canonical"
    if marker not in text:
        text += """\n\ndef test_exact_duplicate_actionable_issues_keep_oldest_canonical(tmp_path: Path) -> None:\n    body = \"- **Target:** `genesis/example.py`\\nFix the exact same defect.\"\n    github = FakeGithub([\n        _issue(560, title=\"[Genesis Detected] Exact defect\", body=body),\n        _issue(562, title=\"[Genesis Detected] Exact defect\", body=body),\n        _issue(563, title=\"[Genesis Detected] Exact defect\", body=body),\n    ])\n\n    result = cleanup_obsolete_github_issues(tmp_path, requester=github)\n\n    assert github.issues[560][\"state\"] == \"open\"\n    assert github.issues[562][\"state\"] == \"closed\"\n    assert github.issues[563][\"state\"] == \"closed\"\n    assert [row[\"github_issue_number\"] for row in result[\"closed\"]] == [562, 563]\n    assert any(row.get(\"managed_kind\") == \"exact_duplicate_canonical\" and row[\"github_issue_number\"] == 560 for row in result[\"kept_current\"])\n\n\ndef test_same_title_with_different_full_body_is_not_exact_duplicate(tmp_path: Path) -> None:\n    github = FakeGithub([\n        _issue(570, title=\"[Genesis Detected] Same title\", body=\"- **Target:** `genesis/example.py`\\nDefect A\"),\n        _issue(571, title=\"[Genesis Detected] Same title\", body=\"- **Target:** `genesis/example.py`\\nDefect B\"),\n    ])\n\n    result = cleanup_obsolete_github_issues(tmp_path, requester=github)\n\n    assert result[\"closed\"] == []\n    assert github.issues[570][\"state\"] == \"open\"\n    assert github.issues[571][\"state\"] == \"open\"\n"""
        cleanup.write_text(text, encoding="utf-8")

    requeue = ROOT / "tests/test_requeue_exhausted_issues.py"
    text = requeue.read_text(encoding="utf-8")
    text = text.replace(
        '    assert ".github/workflows/genesis-bounded-repair-worker.yml" in ENGINE_PATHS\n',
        '    assert ".github/workflows/genesis-bounded-repair-worker.yml" in ENGINE_PATHS\n'
        '    assert ".github/workflows/genesis-sequential-issue-controller.yml" in ENGINE_PATHS\n'
        '    assert "scripts/requeue_exhausted_issues.py" in ENGINE_PATHS\n'
        '    assert "genesis/github_issue_cleanup.py" in ENGINE_PATHS\n',
    )
    text = text.replace(
        'def test_measurement_and_protected_issues_are_not_requeued(tmp_path: Path):',
        'def test_measurement_issues_share_generation_retry_but_protected_targets_do_not(tmp_path: Path):',
    )
    text = text.replace(
        '    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (False, "measurement_lane")',
        '    assert eligible_exhausted_issue(_issue(measured_body, ["genesis-solver-exhausted"]), tmp_path) == (True, "genesis/example.py")',
    )
    requeue.write_text(text, encoding="utf-8")

    policy = ROOT / "tests/test_solver_terminal_policy.py"
    policy.write_text("""from pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_bounded_worker_terminally_defers_exhausted_issue() -> None:\n    text = (ROOT / \".github/workflows/genesis-bounded-repair-worker.yml\").read_text(encoding=\"utf-8\")\n\n    assert \"--add-label genesis-deferred\" in text\n    assert \"-f state=closed -f state_reason=not_planned\" in text\n    assert \"changed repair engine may reopen it automatically\" in text\n\n\ndef test_requeue_wakes_authoritative_sequential_controller() -> None:\n    text = (ROOT / \".github/workflows/genesis-exhausted-issue-requeue.yml\").read_text(encoding=\"utf-8\")\n\n    assert \"--workflow genesis-sequential-issue-controller.yml\" in text\n    assert \"gh workflow run genesis-sequential-issue-controller.yml\" in text\n    assert \"genesis-oldest-issue-solver.yml\" not in text\n""", encoding="utf-8")


def main() -> None:
    patch_cleanup()
    patch_requeue_script()
    patch_worker()
    patch_requeue_workflow()
    patch_tests()


if __name__ == "__main__":
    main()

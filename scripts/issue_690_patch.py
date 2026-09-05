from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch anchor not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


cleanup = ROOT / "genesis" / "github_issue_cleanup.py"
replace_once(
    cleanup,
    'TASK_TYPE_TARGETS = {\n    "benchmark_runner_integration": "genesis/benchmark_execution.py",\n}\n',
    'TASK_TYPE_TARGETS = {\n'
    '    "benchmark_runner_integration": "genesis/benchmark_execution.py",\n'
    '    "frontier_benchmark_measurement": "genesis/benchmark_execution.py",\n'
    '    "capability_growth": "genesis/coding.py",\n'
    '    "model_evaluation": "genesis/model_scout.py",\n'
    '    "competitive_ai_improvement": "genesis/benchmark_execution.py",\n'
    '    "gene_velocity_improvement": "genesis/pulse.py",\n'
    '}\n'
    'EXTERNAL_TERMINAL_PHRASES = (\n'
    '    "external-authority / independent-secret provisioning blocker",\n'
    ')\n'
)
replace_once(
    cleanup,
    '    if not title.startswith("[Genesis Task]"):\n        return None\n',
    '    task_type = _task_type(body)\n'
    '    mapped = TASK_TYPE_TARGETS.get(task_type, "")\n'
    '    model_lab_target = "genesis/model_lab.py" if lower_title.startswith("genesis model lab:") else ""\n'
    '    mapped = mapped or model_lab_target\n'
    '    if not title.startswith("[Genesis Task]") and not mapped:\n'
    '        return None\n'
)
replace_once(
    cleanup,
    '    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):\n        return None\n\n    task_type = _task_type(body)\n    mapped = TASK_TYPE_TARGETS.get(task_type, "")\n    if mapped and _safe_existing_target(root, mapped):\n        return mapped, f"task_type_map:{task_type}"\n',
    '    if mapped and _safe_existing_target(root, mapped):\n'
    '        reason = f"task_type_map:{task_type}" if task_type else "title_map:model_lab"\n'
    '        return mapped, reason\n'
    '    if any(phrase in lower_body for phrase in MEASUREMENT_PHRASES):\n'
    '        return None\n'
)
replace_once(
    cleanup,
    '        if _protected_issue(issue):\n            result["skipped_protected"].append(number)\n            continue\n\n        close_labels = sorted(_issue_labels(issue) & EXPLICIT_CLOSE_LABELS)\n',
    '        if _protected_issue(issue):\n'
    '            result["skipped_protected"].append(number)\n'
    '            remaining.append(issue)\n'
    '            continue\n\n'
    '        lower_body = str(issue.get("body") or "").lower()\n'
    '        if any(phrase in lower_body for phrase in EXTERNAL_TERMINAL_PHRASES):\n'
    '            requester("POST", f"/issues/{number}/comments", {"body": "Genesis Issue Solver terminal reconciliation: the remaining action requires independent external authority/secret provisioning and cannot be performed safely by this repository. Internal code work is complete; closing this Issue as not planned instead of leaving permanent backlog. Reopen only when the external trust-domain evidence is available."})\n'
    '            closed = _close_issue(requester, issue, reason="external_authority_dependency_documented")\n'
    '            if closed is None:\n'
    '                result["blocked"].append({"github_issue_number": number, "reason": "external_terminal_close_failed"})\n'
    '            else:\n'
    '                result["closed"].append(closed)\n'
    '            continue\n\n'
    '        close_labels = sorted(_issue_labels(issue) & EXPLICIT_CLOSE_LABELS)\n'
)
# Cross-family operational/escalation records with the same exact fingerprint should not both stay open.
insert_anchor = '    closed_numbers = {int(row["github_issue_number"]) for row in result["closed"]}\n'
insert_text = '''    fingerprints: dict[str, list[dict]] = {}\n    for issue in remaining:\n        key = _managed_key(issue)\n        if key is not None:\n            fingerprints.setdefault(key[1], []).append(issue)\n    for fingerprint, rows in sorted(fingerprints.items()):\n        kinds = {_managed_key(row)[0] for row in rows if _managed_key(row) is not None}\n        if not {"genesis-ops", "genesis-chatgpt-escalation"}.issubset(kinds):\n            continue\n        ops_rows = [row for row in rows if (_managed_key(row) or ("", ""))[0] == "genesis-ops"]\n        if not ops_rows:\n            continue\n        canonical = max(ops_rows, key=_issue_number)\n        canonical_number = _issue_number(canonical)\n        for row in rows:\n            key = _managed_key(row)\n            number = _issue_number(row)\n            if key is None or key[0] != "genesis-chatgpt-escalation" or number in {0, canonical_number}:\n                continue\n            closed = _close_issue(\n                requester,\n                row,\n                reason=f"escalation_represented_by_ops:{fingerprint}:canonical_issue=#{canonical_number}",\n            )\n            if closed is None:\n                result["blocked"].append({"github_issue_number": number, "reason": "escalation_alias_close_failed"})\n            else:\n                result["closed"].append(closed)\n\n'''
text = cleanup.read_text(encoding="utf-8")
if insert_anchor not in text:
    raise SystemExit("cleanup cross-family insertion anchor missing")
cleanup.write_text(text.replace(insert_anchor, insert_text + insert_anchor, 1), encoding="utf-8")

requeue = ROOT / "scripts" / "requeue_exhausted_issues.py"
replace_once(
    requeue,
    '        batch = _request(repository, token, "GET", f"/issues?state=open&sort=created&direction=asc&per_page=100&page={page}")\n',
    '        batch = _request(repository, token, "GET", f"/issues?state=all&sort=created&direction=asc&per_page=100&page={page}")\n'
)
replace_once(
    requeue,
    '        labels = issue_labels(issue)\n        if labels & (ACTIVE_LABELS | EXHAUSTED_LABELS):\n            continue\n',
    '        labels = issue_labels(issue)\n'
    '        if str(issue.get("state") or "open") != "open":\n'
    '            continue\n'
    '        if labels & (ACTIVE_LABELS | EXHAUSTED_LABELS):\n'
    '            continue\n'
)
replace_once(
    requeue,
    '        for label in ("genesis-solver-exhausted", "genesis-priority-exhausted", "genesis-blocked"):\n',
    '        if str(issue.get("state") or "open") == "closed":\n'
    '            reopened = _request(repository, token, "PATCH", f"/issues/{number}", {"state": "open"})\n'
    '            if not isinstance(reopened, dict) or str(reopened.get("state") or "") != "open":\n'
    '                result["skipped"].append({"issue": number, "reason": "reopen_failed"})\n'
    '                continue\n\n'
    '        for label in ("genesis-solver-exhausted", "genesis-priority-exhausted", "genesis-blocked", "genesis-deferred"):\n'
)

controller = ROOT / ".github" / "workflows" / "genesis-sequential-issue-controller.yml"
replace_once(
    controller,
    "          ensure_label genesis-autonomous 1f883d 'Authorized for Genesis autonomous repair'\n",
    "          ensure_label genesis-autonomous 1f883d 'Authorized for Genesis autonomous repair'\n"
    "          ensure_label genesis-deferred 8c959f 'Closed after bounded solver exhaustion; automatically reopenable after repair-engine change'\n"
)
replace_once(
    controller,
    "          echo 'Safely releasing exhausted issues only when the repair-engine generation changed.'\n",
    "          echo 'Routing and terminally reconciling every open Issue class before selection.'\n"
    "          if ! python -m genesis.github_issue_cleanup; then\n"
    "            echo 'Issue lifecycle preflight reported a partial result; continuing with safely routable work.' >&2\n"
    "          fi\n\n"
    "          echo 'Safely releasing exhausted issues only when the repair-engine generation changed.'\n"
)
replace_once(
    controller,
    "              if 'external-authority / independent-secret provisioning blocker' in lower_body:\n                  continue\n              if lower_title.startswith(('[genesis escalation] ai capability below target', '[genesis ops] ai capability below target')):\n                  continue\n              if lower_title.startswith('genesis model lab:'):\n                  continue\n",
    ""
)
replace_once(
    controller,
    "              requires_measurement = any(\n                  phrase in lower_body\n                  for phrase in (\n                      'post-promotion benchmark', 'post-promotion remeasurement',\n                      'benchmark re-measurement', 'benchmark remeasurement',\n                      'measured score improves', 'same comparable benchmark',\n                  )\n              )\n              if requires_measurement:\n                  continue\n\n",
    ""
)
replace_once(
    controller,
    "              add_label \"$issue_number\" genesis-blocked\n              add_label \"$issue_number\" genesis-solver-exhausted\n              remove_label \"$issue_number\" genesis-autonomous\n",
    "              add_label \"$issue_number\" genesis-blocked\n"
    "              add_label \"$issue_number\" genesis-solver-exhausted\n"
    "              add_label \"$issue_number\" genesis-deferred\n"
    "              remove_label \"$issue_number\" genesis-autonomous\n"
)
replace_once(
    controller,
    "              status_body=$(printf '%s\\n<!-- genesis-solver-attempt:%s -->\\n**Genesis Sequential Issue Controller — bounded attempt exhausted**\\n\\n- Issue: #%s — %s\\n- Last check (UTC): %s\\n- Controller run: %s\\n- Attempt: **%s/%s**\\n- Result: **%s**\\n- State: **blocked until a new repair-engine generation can safely retry it**\\n\\nThe controller did not close this issue because verified completion evidence is missing. The queue may move to the next eligible issue.' \\\n                \"$marker\" \"$attempt\" \"$issue_number\" \"$title\" \"$checked_at\" \"$GITHUB_RUN_ID\" \"$attempt\" \"$max_attempts\" \"$result\")\n",
    "              status_body=$(printf '%s\\n<!-- genesis-solver-attempt:%s -->\\n**Genesis Sequential Issue Controller — bounded attempt exhausted**\\n\\n- Issue: #%s — %s\\n- Last check (UTC): %s\\n- Controller run: %s\\n- Attempt: **%s/%s**\\n- Result: **%s**\\n- State: **terminally deferred; automatically reopenable after repair-engine generation changes**\\n\\nThe current repair generation exhausted its safe attempts. Genesis closes this issue as not planned instead of leaving permanent backlog; a future repair-engine generation can reopen it automatically.' \\\n                \"$marker\" \"$attempt\" \"$issue_number\" \"$title\" \"$checked_at\" \"$GITHUB_RUN_ID\" \"$attempt\" \"$max_attempts\" \"$result\")\n"
)
replace_once(
    controller,
    "            upsert_status \"$issue_number\" \"$status_body\"\n          }\n",
    "            upsert_status \"$issue_number\" \"$status_body\"\n"
    "            if [ \"$attempt\" -ge \"$max_attempts\" ]; then\n"
    "              gh api \"repos/${GITHUB_REPOSITORY}/issues/${issue_number}\" --method PATCH -f state=closed -f state_reason=not_planned >/dev/null\n"
    "            fi\n"
    "          }\n"
)

# Extend focused cleanup tests to lock the new routing/terminal policy.
tests = ROOT / "tests" / "test_github_issue_cleanup.py"
text = tests.read_text(encoding="utf-8")
addition = r'''

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
'''
if "test_frontier_measurement_routes_to_benchmark_execution" not in text:
    tests.write_text(text.rstrip() + addition + "\n", encoding="utf-8")

print("Issue #690 patch applied")

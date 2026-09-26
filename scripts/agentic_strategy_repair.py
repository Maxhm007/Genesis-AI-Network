from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import scripts.github_issue_autorepair as base
from genesis.selfdev import ALLOWED_SCRIPT_PATHS, normalize_selfdev_path
from genesis.issue_target import extract_issue_target
from genesis.github_issue_capability_builder import GitHubIssueLearnedCapabilityProvider


STRATEGY_GUIDANCE = {
    "evidence_first": (
        "Agentic Lab strategy: evidence-first current-state verification. Before proposing ANY edit, inspect current main, "
        "the Issue acceptance criteria, preserved repair memory, and existing focused/regression tests. First decide whether "
        "the objective is already satisfied on current main. If it is already satisfied, do not invent or replay a patch; "
        "preserve evidence that the current implementation and tests satisfy the Issue so orchestration can treat the Issue "
        "as stale/already complete. Only when a concrete remaining gap is demonstrated may you edit, and then prefer the "
        "smallest change that directly addresses that observed gap. Never repeat a rejected candidate merely because the Issue is open."
    ),
    "alternative_implementation": (
        "Agentic Lab strategy: alternative implementation. The prior method failed. Re-check current main and the remaining "
        "acceptance gap first. If the Issue is already satisfied, do not edit. Otherwise use a materially different implementation "
        "path while keeping the same acceptance criteria and exact target scope. Do not reproduce the same control flow, helper "
        "shape, or rejected patch with cosmetic changes."
    ),
    "diagnostic_reframe": (
        "Agentic Lab strategy: diagnostic reframe. Re-check current main before editing. Re-evaluate whether the apparent target "
        "defect is already fixed or is caused by an adjacent invariant, data shape, state transition, or integration assumption "
        "visible in the allowed repository context. Then implement the smallest safe target-local correction only if a real remaining "
        "gap is demonstrated."
    ),
    "dependency_diagnosis": (
        "Agentic Lab strategy: dependency diagnosis. Re-check current main before assuming a dependency. Determine whether the "
        "remaining blocker is lack of a Genesis repair capability, provider/tooling limitation, unavailable dependency, insufficient "
        "safe context, or an Issue whose objective is already satisfied. If a reusable repair capability is genuinely missing, the "
        "orchestration layer will open a capability-building dependency issue. If a safe target-local repair is still necessary, implement "
        "it. Otherwise return without inventing a change."
    ),
    "qwen3_fallback": (
        "Agentic Lab final fallback strategy using the isolated Qwen3 provider. All earlier Agentic strategies already failed on this "
        "same Issue. Read their comments as repair memory, re-check current main and acceptance criteria, and attempt a genuinely new "
        "bounded solution. Do not bypass scope, protected-file, validation, security, promotion, or verify-before-close gates. If no "
        "verified solution can be produced, return failure evidence only; the Issue must remain open and authoritative."
    ),
}

CAPABILITY_LIKE_REASONS = {
    "retry_pending_capability",
    "blocked_no_safe_context",
    "blocked_protected_or_unsupported_target",
}

PROTECTED_SCRIPT_TARGETS = {
    "scripts/secret_guard.py",
    "scripts/privileged_change_gate.py",
    "scripts/verify_validator_votes.py",
    "scripts/action_repair_guard.py",
    "scripts/issue_acceptance_guard.py",
}

BENCHMARK_ADAPTERS = {
    "agents_last_exam": "AgentsLastExamEvidenceAdapter",
    "terminal_bench_2_1": "TerminalBench21EvidenceAdapter",
    "swe_bench_pro": "SWEBenchProEvidenceAdapter",
}
ACTIVE_AGENTIC_LABELS = (
    "genesis-repair-in-progress",
    "genesis-validating",
    "genesis-claimed",
    "genesis-working",
    "genesis-verifying",
    "genesis-blocked",
    "genesis-solver-exhausted",
    "genesis-deferred",
    "genesis-waiting-capability",
    "genesis-needs-human",
    "agentic-lab",
    "genesis-qwen3-agentic",
    "genesis-agentic-escalated",
)

_SCRIPT_TARGET_RE = re.compile(r"(?:^|[\s`'\"(])(scripts/[A-Za-z0-9_./-]+\.py)")
_BENCHMARK_ID_RE = re.compile(r"Make benchmark ([a-z0-9_]+) executable for Genesis")
_TASK_TYPE_RE = re.compile(r"^- \*\*Task type:\*\* `([^`]+)`", re.MULTILINE)
_TARGET_RE = re.compile(r"^- \*\*Target:\*\* `([^`]+)`", re.MULTILINE)


def _explicit_safe_script_paths(issue_text: str, root: Path) -> list[str]:
    rows: list[str] = []
    for raw in _SCRIPT_TARGET_RE.findall(issue_text):
        normalized = raw.replace("\\", "/").removeprefix("./")
        if normalized not in ALLOWED_SCRIPT_PATHS or normalized in PROTECTED_SCRIPT_TARGETS:
            continue
        try:
            normalize_selfdev_path(root, normalized)
        except RuntimeError:
            continue
        if (root / normalized).is_file() and normalized not in rows:
            rows.append(normalized)
    return rows


def _script_aware_context_paths(original, issue_text: str, root: Path, limit: int) -> list[str]:
    explicit_scripts = _explicit_safe_script_paths(issue_text, root)
    if explicit_scripts:
        return explicit_scripts[: max(1, min(int(limit), base.MAX_CONTEXT_FILES))]
    return original(issue_text, root, limit)


def _script_aware_allowed_paths(original, context_paths: list[str]) -> set[str]:
    allowed = set(original(context_paths))
    for relative in context_paths:
        path = Path(relative)
        if relative in ALLOWED_SCRIPT_PATHS and relative not in PROTECTED_SCRIPT_TARGETS:
            allowed.add(f"tests/test_{path.stem}.py")
    return allowed


def _legacy_capability_performance_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    return (
        title.startswith("Genesis Control: Capability Growth")
        and "<!-- genesis-capability-source:" in body
        and "- **Benchmark:**" in body
        and "- **Validated baseline:**" in body
        and "- **Reference:**" in body
        and "Improve the measured Genesis capability gap" in body
    )


def _close_if_legacy_performance_indicator(issue_number: int, repository: str) -> dict | None:
    issue_url = f"https://api.github.com/repos/{repository}/issues/{issue_number}"
    issue = base._api_json("GET", issue_url)
    if not isinstance(issue, dict) or str(issue.get("state") or "").lower() != "open":
        return None
    if not _legacy_capability_performance_issue(issue):
        return None

    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    if not title.startswith("[Performance Indicator]"):
        title = f"[Performance Indicator] {title}"[:240]
    if "<!-- genesis-performance-indicator -->" not in body:
        body = (
            body.rstrip()
            + "\n\n<!-- genesis-performance-indicator -->\n"
            + "### Performance indicator classification\n"
            + "Genesis classified this legacy capability-growth record as a changing benchmark measurement. It stays closed and must not enter DevLab, Issue Solver, Agentic Lab, Qwen3, DeepSeek, or repair retry lanes. Concrete defects or missing capabilities require a separate actionable issue.\n"
        )

    marker = "<!-- genesis-performance-indicator-auto-close -->"
    base._api_json(
        "POST",
        issue_url + "/comments",
        {
            "body": (
                f"{marker}\n"
                "Genesis terminal classification: this legacy capability-growth record is a performance indicator, not immediate repair work. "
                "The changing benchmark value remains measurable over time; concrete defects must use separate actionable Issues. "
                "Agentic repair is stopped and this Issue is closed as not planned."
            )
        },
    )
    closed = base._api_json(
        "PATCH",
        issue_url,
        {
            "title": title,
            "body": body,
            "labels": ["performance-indicator"],
            "state": "closed",
            "state_reason": "not_planned",
        },
    )
    if not isinstance(closed, dict) or str(closed.get("state") or "").lower() != "closed":
        return None
    return {
        "status": "completed",
        "reason": "legacy_capability_growth_performance_indicator",
        "repair_status": "completed",
        "classification": "performance-indicator",
        "issue_number": issue_number,
        "repository": repository,
        "candidate_branch": "",
        "candidate_sha": "",
        "current_state_checked_first": True,
        "full_suite_verified": False,
        "closure_state_reason": "not_planned",
    }


def _benchmark_runner_satisfaction(issue: dict, root: Path) -> dict | None:
    body = str(issue.get("body") or "")
    task_type = _TASK_TYPE_RE.search(body)
    if task_type is None or task_type.group(1).strip() != "benchmark_runner_integration":
        return None
    target = extract_issue_target(body)
    if target != "genesis/benchmark_execution.py":
        return None
    benchmark_match = _BENCHMARK_ID_RE.search(body)
    if benchmark_match is None:
        return None
    benchmark_id = benchmark_match.group(1)
    adapter = BENCHMARK_ADAPTERS.get(benchmark_id)
    if not adapter:
        return None

    planner_path = root / "genesis" / "benchmark_execution.py"
    evidence_path = root / "genesis" / (
        "swe_bench_pro_evidence.py" if benchmark_id == "swe_bench_pro" else
        "terminal_bench_evidence.py" if benchmark_id == "terminal_bench_2_1" else
        "agents_last_exam_evidence.py"
    )
    tests_path = root / "tests" / "test_benchmark_execution.py"
    if not planner_path.is_file() or not evidence_path.is_file() or not tests_path.is_file():
        return None

    planner = planner_path.read_text(encoding="utf-8")
    evidence = evidence_path.read_text(encoding="utf-8")
    tests = tests_path.read_text(encoding="utf-8")
    required = (
        adapter in planner,
        benchmark_id in planner,
        f'if benchmark_id == "{benchmark_id}"' in planner,
        f"{adapter}(self.root).stage(job)" in planner,
        f'class {adapter}' in evidence,
        benchmark_id in tests,
    )
    if not all(required):
        return None

    return {
        "benchmark_id": benchmark_id,
        "target": "genesis/benchmark_execution.py",
        "adapter": adapter,
        "focused_tests": [
            "tests/test_benchmark_execution.py",
            f"tests/test_{benchmark_id}_evidence.py" if benchmark_id != "terminal_bench_2_1" else "tests/test_terminal_bench_evidence.py",
        ],
    }


def _capability_growth_satisfaction(issue: dict, root: Path) -> dict | None:
    body = str(issue.get("body") or "")
    task_type = _TASK_TYPE_RE.search(body)
    if task_type is None or task_type.group(1).strip() != "capability_growth":
        return None
    target = extract_issue_target(body)
    if target != GitHubIssueLearnedCapabilityProvider.CAPABILITY_BUILDER_TARGET:
        return None

    blocked_match = re.search(r"^- \*\*Blocked target:\*\* `([^`]+)`", body, re.MULTILINE)
    blocker_match = re.search(r"^- \*\*Observed blocker:\*\* `([^`]+)`", body, re.MULTILINE)
    if blocked_match is None or blocker_match is None:
        return None
    blocked_target = blocked_match.group(1).replace("\\", "/").lstrip("./")
    blocker = blocker_match.group(1).strip()
    if not GitHubIssueLearnedCapabilityProvider._repairable_capability_blocked_target(blocked_target):
        return None

    builder = root / GitHubIssueLearnedCapabilityProvider.CAPABILITY_BUILDER_TARGET
    tests = root / "tests" / "test_github_issue_capability_builder.py"
    if not builder.is_file() or not tests.is_file():
        return None
    builder_text = builder.read_text(encoding="utf-8")
    tests_text = tests.read_text(encoding="utf-8")

    required_builder = (
        "CAPABILITY_GROWTH_TASK_LINE" in builder_text,
        "CAPABILITY_WORK_MARKER" in builder_text,
        "def _capability_growth_provider(" in builder_text,
        "def _repairable_capability_blocked_target(" in builder_text,
        "EvidenceFirstRepairFollowupProvider" in builder_text,
    )
    required_tests = (
        "test_machine_capability_growth_issue_gets_bounded_self_repair_route" in tests_text,
        "test_capability_growth_allows_safe_dashboard_script_blocker" in tests_text,
        "test_capability_growth_rejects_protected_script_blocker" in tests_text,
    )
    if not all(required_builder + required_tests):
        return None

    return {
        "task_type": "capability_growth",
        "target": target,
        "blocked_target": blocked_target,
        "blocker": blocker,
        "focused_tests": ["tests/test_github_issue_capability_builder.py"],
    }


def _full_suite_passes(root: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    return completed.returncode == 0, output[-4000:]


def _close_if_current_main_satisfies(issue_number: int, repository: str, root: Path = base.ROOT) -> dict | None:
    issue_url = f"https://api.github.com/repos/{repository}/issues/{issue_number}"
    issue = base._api_json("GET", issue_url)
    if not isinstance(issue, dict) or str(issue.get("state") or "").lower() != "open":
        return None
    satisfaction = _benchmark_runner_satisfaction(issue, root)
    if satisfaction is None:
        satisfaction = _capability_growth_satisfaction(issue, root)
    if satisfaction is None:
        return None

    passed, test_output = _full_suite_passes(root)
    if not passed:
        return None

    base._set_labels(
        repository,
        issue_number,
        add=("genesis-verified",),
        remove=ACTIVE_AGENTIC_LABELS,
    )
    marker = "<!-- genesis-current-main-satisfied -->"
    if satisfaction.get("task_type") == "capability_growth":
        detail_lines = (
            "Genesis verified that the current `main` already satisfies this capability-growth issue, so no additional model-generated self-edit is required.\n\n"
            f"- Target: `{satisfaction['target']}`\n"
            f"- Blocked target class: `{satisfaction['blocked_target']}`\n"
            f"- Blocker: `{satisfaction['blocker']}`\n"
            "- Capability route: bounded evidence-first capability-growth adapter present\n"
            "- Regression coverage: safe script blocker allowed; protected script blocker rejected\n"
        )
    else:
        detail_lines = (
            "Genesis verified that the current `main` already satisfies this benchmark-runner integration issue, so no additional model-generated patch is required.\n\n"
            f"- Benchmark: `{satisfaction['benchmark_id']}`\n"
            f"- Target: `{satisfaction['target']}`\n"
            f"- Adapter: `{satisfaction['adapter']}`\n"
        )
    comment = (
        f"{marker}\n"
        + detail_lines
        + "- Verification: full repository `pytest -q` passed on current `main`\n"
        + "- Closure rule: current-state satisfaction verified before close; no successor issue created."
    )
    base._api_json("POST", issue_url + "/comments", {"body": comment})
    closed = base._api_json("PATCH", issue_url, {"state": "closed", "state_reason": "completed"})
    if not isinstance(closed, dict) or str(closed.get("state") or "").lower() != "closed":
        return None
    return {
        "status": "completed",
        "reason": "current_main_already_satisfies_issue",
        "repair_status": "completed",
        "issue_number": issue_number,
        "repository": repository,
        "candidate_branch": "",
        "candidate_sha": "",
        "current_state_checked_first": True,
        "current_main_satisfaction": satisfaction,
        "full_suite_verified": True,
        "full_suite_output_tail": test_output,
    }


def _navigation_landmark_micro_repair(issue: dict, context_paths: list[str], root: Path):
    issue_text = base.build_issue_text(issue)
    lowered = issue_text.lower()
    if "navigation landmark" not in lowered or "aria-label" not in lowered:
        return None
    if len(context_paths) != 1:
        return None
    target = context_paths[0]
    if target not in ALLOWED_SCRIPT_PATHS or target in PROTECTED_SCRIPT_TARGETS:
        return None
    try:
        normalize_selfdev_path(root, target)
    except RuntimeError:
        return None
    path = root / target
    if not path.is_file():
        return None
    current = path.read_text(encoding="utf-8")
    desired = '<nav class="nav" aria-label="Dashboard navigation">'
    if desired in current:
        return None
    insertion = '    html = DASHBOARD.read_text(encoding="utf-8")\n'
    if current.count(insertion) != 1:
        return None
    repair = insertion + '    html = html.replace(\'<nav class="nav">\', \'<nav class="nav" aria-label="Dashboard navigation">\', 1)\n'
    proposed = current.replace(insertion, repair, 1)
    return base.CodingProposal(
        title="Label dashboard navigation landmark",
        rationale="Deterministic micro-repair for an explicitly evidenced missing navigation aria-label.",
        files={target: proposed},
        provider="genesis-agentic-micro-repair",
    )


def _micro_repair_or_original(original, issue: dict, context_paths: list[str], root: Path = base.ROOT, **kwargs):
    micro = _navigation_landmark_micro_repair(issue, context_paths, root)
    if micro is not None:
        return micro
    return original(issue, context_paths, root, **kwargs)


def run(issue_number: int, repository: str, strategy: str) -> dict:
    if strategy not in STRATEGY_GUIDANCE:
        raise ValueError(f"unsupported Agentic Lab strategy: {strategy}")

    performance_indicator = _close_if_legacy_performance_indicator(issue_number, repository)
    if performance_indicator is not None:
        performance_indicator["agentic_strategy"] = strategy
        base.EVIDENCE_PATH.write_text(json.dumps(performance_indicator, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return performance_indicator

    already_satisfied = _close_if_current_main_satisfies(issue_number, repository)
    if already_satisfied is not None:
        already_satisfied["agentic_strategy"] = strategy
        base.EVIDENCE_PATH.write_text(json.dumps(already_satisfied, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return already_satisfied

    original_loader = base.load_maintainer_repair_guidance
    original_context_paths = base.candidate_context_paths
    original_allowed_paths = base.allowed_issue_repair_paths
    original_propose = base.propose_issue_repair
    existing_guidance = original_loader(repository, issue_number)
    strategy_guidance = STRATEGY_GUIDANCE[strategy]

    def load_guidance(_repository: str, _issue_number: int) -> str:
        combined = "\n\n".join(piece for piece in (existing_guidance, strategy_guidance) if piece.strip())
        return combined[: base.MAX_MAINTAINER_GUIDANCE_CHARS]

    def context_paths(issue_text: str, root: Path = base.ROOT, limit: int = base.MAX_CONTEXT_FILES) -> list[str]:
        return _script_aware_context_paths(original_context_paths, issue_text, root, limit)

    def allowed_paths(paths: list[str]) -> set[str]:
        return _script_aware_allowed_paths(original_allowed_paths, paths)

    def propose(issue: dict, paths: list[str], root: Path = base.ROOT, **kwargs):
        return _micro_repair_or_original(original_propose, issue, paths, root, **kwargs)

    base.load_maintainer_repair_guidance = load_guidance
    base.candidate_context_paths = context_paths
    base.allowed_issue_repair_paths = allowed_paths
    base.propose_issue_repair = propose
    try:
        evidence = base.run(issue_number, repository)
    finally:
        base.load_maintainer_repair_guidance = original_loader
        base.candidate_context_paths = original_context_paths
        base.allowed_issue_repair_paths = original_allowed_paths
        base.propose_issue_repair = original_propose

    evidence["agentic_strategy"] = strategy
    evidence["current_state_checked_first"] = True
    reason = str(evidence.get("reason") or evidence.get("repair_status") or "").strip()
    if strategy not in {"dependency_diagnosis", "qwen3_fallback"} and reason in CAPABILITY_LIKE_REASONS:
        evidence["prior_capability_signal"] = reason
        evidence["reason"] = "strategy_requires_more_methods"
        evidence["status"] = "retry_pending"
    base.EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Agentic Lab repair strategy")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--strategy", choices=tuple(STRATEGY_GUIDANCE), required=True)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    print(json.dumps(run(args.issue_number, args.repository, args.strategy), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

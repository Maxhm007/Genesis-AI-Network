from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from genesis.coding import CodingModule
from genesis.devlab.iterative import IterativeGenesisDevLab


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
EVIDENCE_PATH = RUNTIME / "issue_discovery_trial.json"
MAX_SCAN_FILES = 8
MAX_SOURCE_BYTES = 12_000
MAX_TEST_BYTES = 6_000

CONTROL_PLANE_FILES = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
}


def _active_challenge_target(root: Path) -> str:
    path = root / "config" / "genesis_challenge.json"
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if str(payload.get("status", "active")).lower() != "active":
        return ""
    return str(payload.get("target", "")).replace("\\", "/").lstrip("./")


def candidate_files(root: Path, limit: int = MAX_SCAN_FILES) -> list[str]:
    excluded = set(CONTROL_PLANE_FILES)
    active_target = _active_challenge_target(root)
    if active_target:
        excluded.add(active_target)

    rows: list[tuple[int, str]] = []
    base = root / "genesis"
    if not base.is_dir():
        return []
    for path in base.rglob("*.py"):
        if not path.is_file() or "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        rows.append((path.stat().st_size, relative))
    rows.sort(key=lambda item: (item[0], item[1]))
    return [path for _, path in rows[: max(1, min(int(limit), 20))]]


def _bounded_text(path: Path, max_bytes: int) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="ignore")


def discovery_prompt(root: Path, target: str) -> str:
    source = _bounded_text(root / target, MAX_SOURCE_BYTES)
    test_path = root / "tests" / f"test_{Path(target).stem}.py"
    tests = _bounded_text(test_path, MAX_TEST_BYTES) if test_path.is_file() else "No conventional test file exists."
    return (
        "ROLE: genesis_issue_discovery_trial\n"
        "Inspect exactly one low-risk Genesis source file and decide whether it contains a concrete, meaningful software issue. "
        "Look for correctness bugs, unsafe type coercion, edge cases, state mistakes, error-handling defects, or reliability problems. "
        "Do not invent work for style, comments, renaming, or speculative refactoring. Do not propose weakening tests, Security, validation, governance, or promotion. "
        "Return JSON only with keys decision, summary, acceptance, confidence. decision must be issue or no_issue. "
        "If decision=issue, summary must state the observable problem and acceptance must state testable expected behavior without prescribing the implementation.\n"
        f"TARGET: {target}\n"
        f"SOURCE:\n{source}\n"
        f"RELATED_TEST_CONTEXT:\n{tests}\n"
    )


def parse_discovery_response(raw: str) -> dict:
    payload = CodingModule._extract_json(raw)
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in {"issue", "no_issue"}:
        raise ValueError("discovery decision must be issue or no_issue")
    summary = str(payload.get("summary", "")).strip()
    acceptance = str(payload.get("acceptance", "")).strip()
    if decision == "issue" and (not summary or not acceptance):
        raise ValueError("issue discovery requires summary and acceptance")
    return {
        "decision": decision,
        "summary": summary[:2400],
        "acceptance": acceptance[:3000],
        "confidence": payload.get("confidence"),
    }


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


def run_trial(root: Path = ROOT) -> dict:
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    coding = CodingModule(root)
    provider = coding._provider()
    evidence = {
        "status": "started",
        "trigger": "owner_requested_manual_trial",
        "attribution": "owner_triggered_genesis_discovery_execution",
        "autonomous_discovery_credit": False,
        "rule": "The owner triggered this trial but did not choose the discovered issue or implementation. Do not count it as unattended autonomous development.",
        "active_challenge_excluded": _active_challenge_target(root),
        "scanned": [],
        "discovery": None,
        "devlab": None,
    }

    if provider is None:
        evidence.update({"status": "blocked", "reason": "no intelligence provider available"})
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence

    discovered: tuple[str, dict] | None = None
    for target in candidate_files(root):
        try:
            result = parse_discovery_response(provider.reason(discovery_prompt(root, target)))
        except Exception as exc:
            evidence["scanned"].append({"target": target, "status": "provider_error", "error": f"{type(exc).__name__}: {exc}"[:1000]})
            continue
        evidence["scanned"].append({"target": target, **result})
        if result["decision"] == "issue":
            discovered = (target, result)
            break

    if discovered is None:
        evidence["status"] = "no_issue_found"
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence

    target, finding = discovered
    evidence["discovery"] = {"target": target, **finding}
    devlab = IterativeGenesisDevLab(root)
    attempt = devlab.attempt_problem(
        target_path=target,
        problem=finding["summary"],
        acceptance=finding["acceptance"],
        attempt=0,
        previous_error="",
        provider=provider,
        provenance={
            "initiator": "owner.issue_discovery_trial",
            "discovery": "genesis.issue_discovery_trial",
            "designer": "genesis.devlab",
            "executor": "genesis.devlab",
            "attribution": "owner_triggered_genesis_discovery_execution",
        },
    )
    evidence["devlab"] = attempt.as_dict()
    feedback = attempt.feedback
    if not feedback or not feedback.candidate_created or not feedback.tests_passed or not feedback.commit_sha:
        evidence["status"] = "issue_found_solution_failed"
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence

    push = _git("push", "--set-upstream", "origin", feedback.branch)
    if push.returncode != 0:
        evidence.update({"status": "candidate_push_failed", "push_error": push.stderr[-2000:]})
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence

    evidence.update(
        {
            "status": "candidate_created",
            "candidate_branch": feedback.branch,
            "candidate_sha": feedback.commit_sha,
            "tests_passed": True,
        }
    )
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot owner-triggered Genesis issue discovery and DevLab trial")
    parser.parse_args()
    result = run_trial(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

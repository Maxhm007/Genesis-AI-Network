from __future__ import annotations

"""Run internal candidate review against the current main repository state.

Genesis candidates can remain queued while main advances.  The canonical promotion
workflow already rebases an internally-approved exact candidate onto current main,
so internal review should test the same patch/current-main combination instead of
executing the full suite on an obsolete candidate snapshot.

This module changes review execution only.  The original Genesis candidate SHA
remains the approval identity and is restored before handoff to independent
validation/promotion.
"""

import subprocess
from dataclasses import asdict

from .autonomy_pipeline import PipelineRecord, ReviewWorker
from .coding import CodingModule


INSTALL_MARKER = "_genesis_current_main_review_installed"


def _git(worker: ReviewWorker, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=worker.root,
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )


def _normalize(path: object) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def _restore_exact_candidate(worker: ReviewWorker, candidate_sha: str) -> tuple[bool, str]:
    """Restore the exact Genesis candidate as HEAD for the existing handoff contract."""
    _git(worker, "reset", "--hard")
    checkout = _git(worker, "checkout", "--detach", candidate_sha)
    if checkout.returncode != 0:
        return False, "review_candidate_restore_failed:" + checkout.stderr[-1200:]
    head = _git(worker, "rev-parse", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != candidate_sha:
        return False, "review_candidate_restore_mismatch"
    return True, ""


def _prepare_candidate_on_current_main(
    worker: ReviewWorker,
    record: PipelineRecord,
) -> tuple[bool, str, str, str]:
    """Apply only the exact candidate patch to current main without committing it.

    Returns (ok, feedback, diff, current_main_sha).  A clean application is a
    compatibility precondition, not an approval.  Tests, model review, independent
    validators, security, and promotion still run afterward.
    """
    candidate_sha = str(record.candidate_sha or "")
    review_ref = str(record.review_ref or "")
    target = _normalize(record.target_path)
    if not candidate_sha or not review_ref or not target:
        return False, "review_candidate_metadata_missing", "", ""

    fetched = _git(
        worker,
        "fetch",
        "origin",
        f"{review_ref}:refs/remotes/origin/{review_ref}",
    )
    if fetched.returncode != 0:
        return False, "review_candidate_fetch_failed:" + fetched.stderr[-1200:], "", ""
    exists = _git(worker, "cat-file", "-e", f"{candidate_sha}^{{commit}}")
    if exists.returncode != 0:
        return False, "review_candidate_not_available", "", ""

    changed = _git(
        worker,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        f"{candidate_sha}^",
        candidate_sha,
    )
    changed_files = [
        _normalize(line)
        for line in changed.stdout.splitlines()
        if _normalize(line)
    ]
    if changed.returncode != 0 or changed_files != [target]:
        return (
            False,
            "internal_review_candidate_scope_mismatch:" + repr(changed_files),
            "",
            "",
        )

    patch_result = _git(
        worker,
        "diff",
        f"{candidate_sha}^",
        candidate_sha,
        "--",
        target,
    )
    patch = patch_result.stdout
    if patch_result.returncode != 0 or not patch.strip():
        return False, "internal_review_candidate_patch_missing", "", ""

    fetched_main = _git(worker, "fetch", "origin", "main")
    if fetched_main.returncode != 0:
        return False, "internal_review_main_fetch_failed:" + fetched_main.stderr[-1200:], "", ""
    main_sha_result = _git(worker, "rev-parse", "origin/main")
    if main_sha_result.returncode != 0:
        return False, "internal_review_main_sha_missing", "", ""
    main_sha = main_sha_result.stdout.strip()

    checkout = _git(worker, "checkout", "--detach", "origin/main")
    if checkout.returncode != 0:
        return False, "internal_review_main_checkout_failed:" + checkout.stderr[-1200:], "", main_sha
    reset = _git(worker, "reset", "--hard", "origin/main")
    if reset.returncode != 0:
        return False, "internal_review_main_reset_failed:" + reset.stderr[-1200:], "", main_sha

    check = _git(worker, "apply", "--check", "-", input_text=patch)
    if check.returncode != 0:
        return (
            False,
            "internal_review_current_main_patch_conflict:" + check.stderr[-1200:],
            "",
            main_sha,
        )
    applied = _git(worker, "apply", "-", input_text=patch)
    if applied.returncode != 0:
        return (
            False,
            "internal_review_current_main_patch_apply_failed:" + applied.stderr[-1200:],
            "",
            main_sha,
        )

    working_changed = _git(worker, "diff", "--name-only")
    working_files = [
        _normalize(line)
        for line in working_changed.stdout.splitlines()
        if _normalize(line)
    ]
    if working_changed.returncode != 0 or working_files != [target]:
        return (
            False,
            "internal_review_staged_scope_mismatch:" + repr(working_files),
            "",
            main_sha,
        )

    diff_result = _git(worker, "diff", "--", target)
    diff = diff_result.stdout
    if diff_result.returncode != 0 or not diff.strip():
        return False, "internal_review_staged_diff_missing", "", main_sha
    return True, "", diff, main_sha


def _fail(worker: ReviewWorker, record: PipelineRecord, feedback: str) -> dict:
    if record.candidate_sha:
        _restore_exact_candidate(worker, str(record.candidate_sha))
    return worker._send_back(record, feedback)


def _run_review_on_current_main(worker: ReviewWorker, record: PipelineRecord) -> dict:
    if not record.candidate_sha or not record.candidate_branch or not record.review_ref:
        return worker._send_back(record, "review_candidate_metadata_missing")

    ok, feedback, diff, review_base_sha = _prepare_candidate_on_current_main(worker, record)
    if not ok:
        return _fail(worker, record, feedback)

    tests = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        cwd=worker.root,
        text=True,
        capture_output=True,
        check=False,
        timeout=900,
    )
    test_output = (tests.stdout + "\n" + tests.stderr)[-worker.MAX_FEEDBACK_BYTES :]
    if tests.returncode != 0:
        return _fail(worker, record, "internal_full_test_failure_on_current_main:\n" + test_output)

    task = worker.engineering.queue.get(record.task_id)
    if task is None:
        return _fail(worker, record, "review_task_missing")

    diff = diff.encode("utf-8", errors="replace")[: worker.MAX_DIFF_BYTES].decode(
        "utf-8", errors="replace"
    )
    provider = worker.engineering.coding._provider()
    if provider is None or str(getattr(provider, "name", "")) == "genesis-bootstrap":
        return _fail(worker, record, "internal_review_requires_non_bootstrap_provider")

    prompt = (
        "ROLE: genesis_internal_code_reviewer\n"
        "Review this already test-passing Genesis candidate independently from the implementation or repair attempt. "
        "The exact candidate patch has been replayed on CURRENT MAIN and the full repository test suite passed there. "
        "Return JSON only with decision and feedback. decision must be approve or needs_repair. "
        "Approve only if the candidate addresses the objective without unrelated behavior changes, hidden regressions, "
        "or weakened safety/validation boundaries. Do not ask for style-only refactoring.\n"
        f"OBJECTIVE: {task.objective}\n"
        f"TARGET: {record.target_path}\n"
        f"ORIGINAL_CANDIDATE_SHA: {record.candidate_sha}\n"
        f"CURRENT_MAIN_SHA: {review_base_sha}\n"
        f"TEST_RESULT_ON_CURRENT_MAIN: pass\n"
        f"DIFF:\n{diff}\n"
    )
    try:
        payload = CodingModule._extract_json(provider.reason(prompt))
    except Exception as exc:
        return _fail(
            worker,
            record,
            f"internal_review_provider_error:{type(exc).__name__}:{exc}",
        )
    decision = str(payload.get("decision") or "").strip().lower()
    reviewer_feedback = str(payload.get("feedback") or "").strip()[: worker.MAX_FEEDBACK_BYTES]
    if decision != "approve":
        return _fail(
            worker,
            record,
            reviewer_feedback or "internal_reviewer_requested_revision",
        )

    restored, restore_error = _restore_exact_candidate(worker, str(record.candidate_sha))
    if not restored:
        return worker._send_back(record, restore_error)

    updated = worker.store.transition(
        record.task_id,
        "validation_ready",
        worker="review",
        feedback=reviewer_feedback or f"internal_review_approved_on_current_main:{review_base_sha}",
        bump_review=True,
    )
    return {
        "action": "pipeline_internal_review_approved",
        "record": asdict(updated),
        "validation_candidate": {
            "branch": record.candidate_branch,
            "candidate_sha": record.candidate_sha,
        },
        "review_base_sha": review_base_sha,
        "review_mode": "exact_patch_on_current_main",
    }


def install_current_main_review() -> None:
    """Install once without changing any promotion or validation authority."""
    if getattr(ReviewWorker, INSTALL_MARKER, False):
        return
    ReviewWorker.run = _run_review_on_current_main
    setattr(ReviewWorker, INSTALL_MARKER, True)

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.coding import CodingModule
from genesis.devlab.iterative import IterativeGenesisDevLab
from genesis.file_self_review_policy import QuorumFileSelfReviewLoop
from genesis.selfdev import SelfDevelopmentExecutor


CHALLENGE_PATH = "config/genesis_challenge.json"
MAX_ASSIGNED_CHALLENGE_ATTEMPTS = 2


def _challenge_spec(root: Path) -> dict | None:
    path = root / CHALLENGE_PATH
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("status", "active")).lower() != "active":
        return None

    target = str(payload.get("target", "")).replace("\\", "/").lstrip("./")
    problem = str(payload.get("problem", "")).strip()
    acceptance = str(payload.get("acceptance", "")).strip()
    method = str(payload.get("method", "minimal_correctness_fix")).strip()
    ephemeral_files = payload.get("ephemeral_acceptance_files", {})
    if not isinstance(ephemeral_files, dict):
        raise ValueError("ephemeral_acceptance_files must be a mapping of test path to source")
    ephemeral_files = {str(path): str(content) for path, content in ephemeral_files.items()}
    if not target or not problem or not (root / target).is_file():
        raise ValueError("active Genesis challenge requires an existing target and a problem statement")

    return {
        "target": target,
        "problem": problem,
        "acceptance": acceptance or problem,
        "method": method,
        "ephemeral_acceptance_files": ephemeral_files,
    }


def _candidate_created(attempt) -> bool:
    feedback = attempt.feedback
    return bool(
        feedback
        and feedback.candidate_created
        and feedback.tests_passed
        and feedback.commit_sha
        and feedback.branch
    )


def _attempt_failure(attempt) -> str:
    feedback = attempt.feedback
    if feedback and feedback.failure:
        return str(feedback.failure)[-2000:]
    return str(getattr(attempt, "status", "assigned challenge attempt failed"))[-2000:]


def _run_assigned_challenge(root: Path):
    """Execute an owner-assigned challenge through Genesis's iterative DevLab.

    The owner supplies the problem and acceptance criteria only. Genesis remains
    responsible for diagnosis, implementation, test-feedback repair, and candidate
    creation. This path deliberately reuses the same isolated iterative DevLab
    loop as the golden engineering path instead of performing a single proposal.

    Optional executable acceptance tests are challenge evidence only: DevLab
    installs them into its disposable worktree, but they never become candidate
    files and therefore cannot place a known failing suite on ``main``.

    One failed bounded DevLab cycle is fed into one second outer strategy. The
    inner DevLab already performs edit/test/revise recovery, so this avoids
    multiplying slow local-model calls while retaining failure-analysis feedback.
    """
    spec = _challenge_spec(root)
    if spec is None:
        return None

    coding = CodingModule(root)
    provider = coding._provider()
    if provider is None:
        raise RuntimeError("no intelligence provider available for assigned Genesis challenge")

    problem = (
        f"{spec['problem']} Approach guidance: {spec['method']}. "
        "Diagnose the current source yourself and make the smallest correct edit."
    )
    devlab = IterativeGenesisDevLab(root, coding.providers)
    previous_error = ""
    attempt = None
    for attempt_index in range(MAX_ASSIGNED_CHALLENGE_ATTEMPTS):
        attempt = devlab.attempt_problem(
            target_path=spec["target"],
            problem=problem,
            acceptance=spec["acceptance"],
            attempt=attempt_index,
            previous_error=previous_error,
            provider=provider,
            provenance={
                "initiator": "owner.assigned_challenge",
                "discovery": "owner.assigned_challenge",
                "designer": "genesis.devlab",
                "executor": "genesis.devlab",
                "attribution": "owner_initiated",
            },
            ephemeral_files=spec["ephemeral_acceptance_files"],
        )
        if _candidate_created(attempt):
            break
        previous_error = _attempt_failure(attempt)
        if getattr(attempt, "status", "") == "retry_exhausted":
            break

    if attempt is None:
        raise RuntimeError("assigned Genesis challenge did not execute")
    return spec, attempt


def _push_candidate(root: Path, branch: str) -> None:
    subprocess.run(["git", "push", "--set-upstream", "origin", branch], cwd=root, check=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = QuorumFileSelfReviewLoop(root)

    challenge = _run_assigned_challenge(root)
    if challenge is not None:
        spec, attempt = challenge
        feedback = attempt.feedback
        candidate_created = _candidate_created(attempt)
        payload = {
            "status": "candidate_created" if candidate_created else "candidate_failed",
            "source": "assigned_challenge",
            "plan": {
                "title": f"Genesis assigned challenge: {spec['target']}",
                "rationale": spec["problem"],
                "method": spec["method"],
                "max_outer_attempts": MAX_ASSIGNED_CHALLENGE_ATTEMPTS,
                "ephemeral_acceptance_files": sorted(spec["ephemeral_acceptance_files"]),
            },
            "devlab": attempt.as_dict(),
            "file_self_review": loop.status(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))

        if candidate_created:
            _push_candidate(root, feedback.branch)
            return

        subprocess.run(["git", "checkout", "main"], cwd=root, check=False, capture_output=True, text=True)
        return

    plan = loop.plan_next()
    if plan is None:
        print(json.dumps({"status": "review_recorded_or_retry_pending", "source": "intrinsic_file_review", "file_self_review": loop.status()}, indent=2, sort_keys=True))
        return

    executor = SelfDevelopmentExecutor(root)
    result = executor.execute(dict(plan["proposal"]))
    loop.observe_execution(dict(plan["proposal"]), result)

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "source": "intrinsic_file_review",
        "plan": {"title": plan["title"], "rationale": plan["rationale"]},
        "result": asdict(result),
        "file_self_review": loop.status(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if result.tests_passed and result.committed and result.commit_sha:
        _push_candidate(root, result.branch)
        return

    subprocess.run(["git", "checkout", "main"], cwd=root, check=False, capture_output=True, text=True)


if __name__ == "__main__":
    main()

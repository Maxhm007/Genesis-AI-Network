from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from genesis.coding import CodingModule
from genesis.file_self_review_policy import QuorumFileSelfReviewLoop
from genesis.selfdev import SelfDevelopmentExecutor


CHALLENGE_PATH = "config/genesis_challenge.json"


def _challenge_plan(root: Path) -> dict | None:
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
    if not target or not problem or not (root / target).is_file():
        raise ValueError("active Genesis challenge requires an existing target and a problem statement")

    coding = CodingModule(root)
    provider = coding._provider()
    if provider is None:
        raise RuntimeError("no intelligence provider available for assigned Genesis challenge")

    objective = (
        f"ASSIGNED_SELF_REVIEW_CHALLENGE. Target exactly {target}. "
        f"Problem to solve: {problem} Acceptance criteria: {acceptance} "
        f"Approach: {method}. Diagnose the source yourself and make the smallest correct edit. "
        "Do not edit any other file and do not weaken validation or tests."
    )
    context = [target]
    test_path = f"tests/test_{Path(target).stem}.py"
    if (root / test_path).is_file():
        context.append(test_path)
    proposal = coding.propose(objective, context_paths=context, provider=provider)
    if set(proposal.files) != {target}:
        raise ValueError("assigned challenge proposal attempted to modify a non-target file")

    return {
        "title": f"Genesis assigned challenge: {target}",
        "rationale": problem,
        "proposal": {
            "title": f"Solve assigned review challenge for {target}",
            "rationale": proposal.rationale,
            "files": proposal.files,
            "provenance": {
                "initiator": "owner.assigned_challenge",
                "discovery": "owner.assigned_challenge",
                "designer": "genesis.coding",
            },
            "assigned_challenge": {
                "target": target,
                "problem": problem,
                "acceptance": acceptance,
                "method": method,
            },
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    loop = QuorumFileSelfReviewLoop(root)
    plan = _challenge_plan(root)
    source = "assigned_challenge" if plan is not None else "intrinsic_file_review"
    if plan is None:
        plan = loop.plan_next()

    if plan is None:
        print(json.dumps({"status": "review_recorded_or_retry_pending", "source": source, "file_self_review": loop.status()}, indent=2, sort_keys=True))
        return

    executor = SelfDevelopmentExecutor(root)
    result = executor.execute(dict(plan["proposal"]))
    if source == "intrinsic_file_review":
        loop.observe_execution(dict(plan["proposal"]), result)

    payload = {
        "status": "candidate_created" if result.tests_passed and result.committed else "candidate_failed",
        "source": source,
        "plan": {"title": plan["title"], "rationale": plan["rationale"]},
        "result": asdict(result),
        "file_self_review": loop.status(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if result.tests_passed and result.committed and result.commit_sha:
        subprocess.run(["git", "push", "--set-upstream", "origin", result.branch], cwd=root, check=True)
        return

    subprocess.run(["git", "checkout", "main"], cwd=root, check=False, capture_output=True, text=True)


if __name__ == "__main__":
    main()

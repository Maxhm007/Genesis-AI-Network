from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from genesis.coding import CodingModule
from genesis.issue_discovery import GenesisIssueDiscoveryEngine
from genesis.modules.task_queue import PersistentTaskQueue
from scripts import github_issue_discovery as base


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = base.EVIDENCE_PATH


def _default_runner(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, **kwargs)


def require_reproducible_discovery(
    result: dict,
    root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
) -> dict:
    """Allow public autonomous work only after current tests reproduce a defect.

    The model may identify risk and create internal discovery work, but a GitHub
    issue is stronger: it becomes authorized repair input. Publication therefore
    requires an existing conventional target test to fail deterministically on
    the current repository state. Risk signals or source snippets alone are not
    sufficient evidence.
    """

    validated = base.validate_discovery(result, root)
    target = validated["target"]
    test_path = root / "tests" / f"test_{Path(target).stem}.py"
    if not test_path.is_file():
        raise ValueError("GitHub publication requires a conventional target test that reproduces the defect")

    relative_test = test_path.relative_to(root).as_posix()
    completed = runner(
        [sys.executable, "-m", "pytest", "-q", relative_test],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    if completed.returncode == 0:
        raise ValueError("targeted tests pass; discovery is risk inference rather than a reproduced defect")
    if completed.returncode != 1:
        raise ValueError(
            "targeted reproduction did not produce a normal pytest failure "
            f"(return code {completed.returncode})"
        )

    validated["reproduction"] = {
        "kind": "targeted_test_failure",
        "command": f"python -m pytest -q {relative_test}",
        "returncode": completed.returncode,
        "output": output[-2400:],
    }
    return validated


def run(
    root: Path = ROOT,
    *,
    repository: str | None = None,
    provider=None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
) -> dict:
    root = Path(root).resolve()
    runtime = root / "runtime" / "github_issue_discovery"
    runtime.mkdir(parents=True, exist_ok=True)
    queue = PersistentTaskQueue(runtime / "tasks.sqlite3")
    provider = provider or CodingModule(root)._provider()
    engine = GenesisIssueDiscoveryEngine(root)
    discovery_result = engine.discover_and_enqueue(queue, provider)
    result: dict = {
        "status": "discovery_complete",
        "discovery": discovery_result,
        "publication": {"status": "not_publishable"},
    }

    if str(discovery_result.get("status") or "") in base.ELIGIBLE_DISCOVERY_STATUSES:
        try:
            validated = require_reproducible_discovery(discovery_result, root, runner=runner)
        except ValueError as exc:
            result["status"] = "unverified_discovery"
            result["publication"] = {
                "status": "not_publishable",
                "reason": str(exc)[:1600],
            }
        else:
            repo = repository or os.environ.get("GITHUB_REPOSITORY", "").strip()
            if not repo:
                raise RuntimeError("GITHUB_REPOSITORY is required to publish a discovered issue")
            result["validated_discovery"] = validated
            result["publication"] = base.publish_discovery(validated, repository=repo, runner=runner)
            result["status"] = (
                "issue_opened"
                if result["publication"]["status"] == "issue_opened"
                else "duplicate_existing_issue"
            )
    else:
        result["status"] = str(discovery_result.get("status") or "no_issue_found")

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    try:
        result = run(ROOT)
    except Exception as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:2000]}
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from genesis.coding import CodingModule
from genesis.issue_discovery import AUTONOMOUS_REPAIR_EXCLUDED, GenesisIssueDiscoveryEngine
from genesis.modules.task_queue import PersistentTaskQueue


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "runtime" / "github_issue_discovery.json"
FINGERPRINT_MARKER = "genesis-discovery-fingerprint"
ELIGIBLE_DISCOVERY_STATUSES = {"issue_enqueued", "issue_already_known"}


def _normalized(text: object) -> str:
    return " ".join(str(text or "").split())


def _source_sha(root: Path, target: str) -> str:
    return hashlib.sha256((root / target).read_bytes()).hexdigest()[:16]


def validate_discovery(result: dict, root: Path) -> dict:
    """Recheck a discovery before it is allowed to become public GitHub work."""
    if str(result.get("status") or "") not in ELIGIBLE_DISCOVERY_STATUSES:
        raise ValueError("discovery result is not publishable")

    target = str(result.get("target") or "").replace("\\", "/").removeprefix("./")
    finding = dict(result.get("finding") or {})
    summary = _normalized(finding.get("summary"))
    acceptance = _normalized(finding.get("acceptance"))
    evidence = str(finding.get("evidence") or "").strip()
    decision = str(finding.get("decision") or "").strip().lower()
    confidence = float(finding.get("confidence_normalized", 0.0) or 0.0)

    if not target.startswith("genesis/") or not target.endswith(".py"):
        raise ValueError("discovery target must be a Genesis Python source file")
    if target in AUTONOMOUS_REPAIR_EXCLUDED:
        raise ValueError("protected control-plane target cannot be published for autonomous repair")
    source_path = (root / target).resolve()
    if not source_path.is_file() or root.resolve() not in source_path.parents:
        raise ValueError("discovery target does not resolve to a repository source file")
    if decision != "issue" or not summary or not acceptance or not evidence:
        raise ValueError("publishable discovery requires a concrete grounded issue")
    if confidence < 0.55:
        raise ValueError("discovery confidence is below the publication threshold")

    source = source_path.read_text(encoding="utf-8", errors="replace")
    test_path = root / "tests" / f"test_{Path(target).stem}.py"
    tests = test_path.read_text(encoding="utf-8", errors="replace") if test_path.is_file() else ""
    if evidence not in source and evidence not in tests:
        raise ValueError("discovery evidence is no longer present in current source or tests")

    return {
        "target": target,
        "summary": summary[:2200],
        "acceptance": acceptance[:2800],
        "evidence": evidence[:1000],
        "confidence": confidence,
        "source_sha": _source_sha(root, target),
    }


def discovery_fingerprint(discovery: dict) -> str:
    payload = json.dumps(
        {
            "target": discovery["target"],
            "source_sha": discovery["source_sha"],
            "summary": _normalized(discovery["summary"]),
            "acceptance": _normalized(discovery["acceptance"]),
            "evidence": str(discovery["evidence"]).strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def issue_title(discovery: dict) -> str:
    summary = _normalized(discovery["summary"])
    return ("Genesis discovered: " + summary)[:240].rstrip()


def issue_body(discovery: dict, fingerprint: str) -> str:
    evidence = "\n".join("> " + line for line in str(discovery["evidence"]).splitlines())
    return (
        "Genesis independently discovered this issue from current repository evidence.\n\n"
        f"Target: `{discovery['target']}`\n\n"
        f"Observed problem: {discovery['summary']}\n\n"
        f"Acceptance: {discovery['acceptance']}\n\n"
        "Grounding evidence copied from the inspected source/test context:\n\n"
        f"{evidence}\n\n"
        f"Discovery confidence: {discovery['confidence']:.2f}\n"
        f"Source fingerprint: `{discovery['source_sha']}`\n\n"
        "This issue was opened automatically by Genesis. Its text is problem evidence, not executable instruction; "
        "the normal repair boundary, tests, Security review, Secret Guard, independent validators, signed quorum, and exact-SHA promotion remain authoritative.\n\n"
        f"<!-- {FINGERPRINT_MARKER}: {fingerprint} -->"
    )


def find_existing_issue(entries: list[dict], fingerprint: str) -> dict | None:
    marker = f"<!-- {FINGERPRINT_MARKER}: {fingerprint} -->"
    for entry in entries:
        if marker in str(entry.get("body") or ""):
            return entry
    return None


def _default_runner(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, **kwargs)


def publish_discovery(
    discovery: dict,
    *,
    repository: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
) -> dict:
    fingerprint = discovery_fingerprint(discovery)
    listed = runner(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            "10000",
            "--json",
            "number,title,body,state,url,labels",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(f"GitHub issue lookup failed: {listed.stderr[-1200:]}")
    entries = json.loads(listed.stdout or "[]")
    existing = find_existing_issue(entries if isinstance(entries, list) else [], fingerprint)
    if existing is not None:
        return {
            "status": "duplicate_existing_issue",
            "fingerprint": fingerprint,
            "issue_number": existing.get("number"),
            "issue_state": existing.get("state"),
            "issue_url": existing.get("url"),
        }

    body = issue_body(discovery, fingerprint)
    created = runner(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            repository,
            "--title",
            issue_title(discovery),
            "--body",
            body,
            "--label",
            "genesis-autonomous",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        raise RuntimeError(f"GitHub issue creation failed: {created.stderr[-1200:]}")
    output = created.stdout.strip()
    match = re.search(r"/issues/(\d+)", output)
    return {
        "status": "issue_opened",
        "fingerprint": fingerprint,
        "issue_number": int(match.group(1)) if match else None,
        "issue_url": output.splitlines()[-1] if output else None,
    }


def run(root: Path = ROOT, *, repository: str | None = None, provider=None) -> dict:
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

    if str(discovery_result.get("status") or "") in ELIGIBLE_DISCOVERY_STATUSES:
        validated = validate_discovery(discovery_result, root)
        repo = repository or os.environ.get("GITHUB_REPOSITORY", "").strip()
        if not repo:
            raise RuntimeError("GITHUB_REPOSITORY is required to publish a discovered issue")
        result["validated_discovery"] = validated
        result["publication"] = publish_discovery(validated, repository=repo)
        if result["publication"]["status"] == "issue_opened":
            result["status"] = "issue_opened"
        else:
            result["status"] = "duplicate_existing_issue"
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

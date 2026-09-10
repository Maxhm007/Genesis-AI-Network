from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import github_issue_autorepair as base


ROOT = Path(__file__).resolve().parents[1]
MOBILE_CONTEXT = (
    "mobile/app/src/main/java/org/genesisai/mobile/MainActivity.java",
    "mobile/app/src/main/java/org/genesisai/mobile/GenesisDashboard.java",
    "mobile/app/src/main/java/org/genesisai/mobile/EmergencyPulseEngine.java",
    "mobile/app/src/main/AndroidManifest.xml",
    "mobile/app/build.gradle",
    "mobile/build.gradle",
)


def _existing_mobile_context(root: Path = ROOT) -> list[str]:
    return [path for path in MOBILE_CONTEXT if (root / path).is_file()]


def run(issue_number: int, repository: str) -> dict:
    issue = base.fetch_issue(repository, issue_number)
    title = str(issue.get("title") or "").lower()
    body = str(issue.get("body") or "").lower()
    if "android" not in title + "\n" + body and "application_development" not in body:
        raise RuntimeError("Android repair adapter only accepts Android/application-development issues")

    context = _existing_mobile_context(ROOT)
    if not context:
        raise RuntimeError("no Android mobile source context is available")

    original_explicit = base._explicit_genesis_paths
    original_context = base.candidate_context_paths

    def mobile_explicit(_text: str) -> list[str]:
        return context

    def mobile_context(_text: str, root: Path = ROOT, limit: int = base.MAX_CONTEXT_FILES) -> list[str]:
        bounded = max(1, min(int(limit), base.MAX_CONTEXT_FILES))
        return _existing_mobile_context(root)[:bounded]

    base._explicit_genesis_paths = mobile_explicit
    base.candidate_context_paths = mobile_context
    try:
        evidence = base.run(issue_number, repository)
    finally:
        base._explicit_genesis_paths = original_explicit
        base.candidate_context_paths = original_context

    evidence["repair_lane"] = "android_mobile"
    evidence["mobile_context"] = context
    base.EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Android issue repair")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    print(json.dumps(run(args.issue_number, args.repository), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Genesis protected-path gate (report-only first stage).

This file lives under .github/workflows/, which the built-in workflow token
can never change, so the bot cannot rewrite the gate or its manifest.

Checks, independent of commit author (author names can be set to anything):
1. Every locked file at HEAD matches the sha256 in manifest.json.
2. A commit that changes a locked file must also update manifest.json in the
   same commit (only a maintainer landing through .github/ can do that).
3. Every other commit's Python/text changes pass the independent change
   reviewer, loaded from its exact, hash-verified file.
4. No workflow other than this gate holds `actions: write`.

In report-only mode the findings go to the job summary and the exit code is 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

GATE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = ".github/workflows/gate/manifest.json"
GATE_WORKFLOW = ".github/workflows/genesis-protected-gate.yml"
ACTIONS_WRITE_RE = re.compile(r"^\s*actions:\s*write\s*$", re.MULTILINE)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def file_at(root: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_manifest(root: Path) -> dict:
    return json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))


def check_hashes(root: Path, manifest: dict) -> list[str]:
    findings = []
    for path, expected in sorted(manifest["files"].items()):
        target = root / path
        if not target.is_file():
            findings.append(f"locked file missing: {path}")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            findings.append(f"locked file changed without a manifest update: {path}")
    return findings


def load_reviewer(root: Path, manifest: dict):
    """Run the hash-verified reviewer source directly, never via imports."""
    for name in ("genesis/log_redaction.py", "genesis/change_review.py"):
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["files"].get(name):
            return None
    package = types.ModuleType("_genesis_gate_review")
    package.__path__ = []
    sys.modules[package.__name__] = package
    loaded = None
    for name in ("log_redaction", "change_review"):
        module = types.ModuleType(f"{package.__name__}.{name}")
        module.__package__ = package.__name__
        module.__file__ = str(root / "genesis" / f"{name}.py")
        sys.modules[module.__name__] = module
        source = (root / "genesis" / f"{name}.py").read_text(encoding="utf-8")
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        loaded = module
    return loaded


def changed_files(root: Path, commit: str) -> list[str]:
    out = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit)
    return [line for line in out.splitlines() if line]


def check_commit(root: Path, commit: str, manifest: dict, reviewer) -> list[str]:
    findings = []
    paths = changed_files(root, commit)
    maintainer_landed = MANIFEST_PATH in paths or any(p.startswith(".github/workflows/") for p in paths)
    locked = set(manifest["files"])
    for path in paths:
        if path in locked and MANIFEST_PATH not in paths:
            findings.append(f"{commit[:8]} changes locked file {path} without updating the manifest")
    if maintainer_landed or reviewer is None:
        return findings
    parent = f"{commit}^"
    for path in paths:
        if not path.endswith((".py", ".md", ".json", ".yml", ".yaml", ".txt", ".toml", ".cfg")):
            continue
        new = file_at(root, commit, path)
        if new is None:
            continue
        old = file_at(root, parent, path) or ""
        for finding in reviewer.review_change(path, old, new):
            findings.append(f"{commit[:8]} {finding.render()}")
    return findings


def check_workflows(root: Path) -> list[str]:
    findings = []
    for workflow in sorted((root / ".github/workflows").glob("*.y*ml")):
        relative = workflow.relative_to(root).as_posix()
        if relative == GATE_WORKFLOW:
            continue
        if ACTIONS_WRITE_RE.search(workflow.read_text(encoding="utf-8")):
            findings.append(f"workflow other than the gate has actions: write: {relative}")
    return findings


def commits_to_check(root: Path, since: str | None, limit: int) -> list[str]:
    spec = [f"{since}..HEAD"] if since else ["-n", str(limit), "HEAD"]
    return list(reversed(git(root, "rev-list", *spec).split()))


def run(root: Path, since: str | None, limit: int) -> dict:
    manifest = load_manifest(root)
    hash_findings = check_hashes(root, manifest)
    reviewer = load_reviewer(root, manifest)
    commit_findings: list[str] = []
    for commit in commits_to_check(root, since, limit):
        commit_findings.extend(check_commit(root, commit, manifest, reviewer))
    return {
        "hashes": hash_findings,
        "reviewer_loaded": reviewer is not None,
        "commits": commit_findings,
        "workflows": check_workflows(root),
    }


def render(result: dict, report_only: bool) -> str:
    blocking = result["hashes"] + result["commits"] + ([] if result["reviewer_loaded"] else ["reviewer failed hash check; commit review skipped"])
    lines = ["## Genesis protected-path gate" + (" (report-only)" if report_only else "")]
    lines.append("Result: " + ("WOULD FAIL" if blocking and report_only else "FAIL" if blocking else "pass"))
    for title, rows in (("Locked file hashes", result["hashes"]), ("Commits", result["commits"]), ("Workflow permissions", result["workflows"])):
        lines.append(f"### {title}: {len(rows)} finding(s)")
        lines.extend(f"- {row}" for row in rows[:200])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--since", default=os.environ.get("GATE_SINCE") or None)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = run(root, args.since, args.limit)
    report = render(result, args.report_only)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    blocking = result["hashes"] or result["commits"] or not result["reviewer_loaded"]
    return 0 if args.report_only or not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())

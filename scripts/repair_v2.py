"""One-file, evidence-gated reciprocal code repair. No peer conversations.

prepare: unprivileged job asks a model for a small Python diff after a repeated
         failed test run in the OTHER repository.
validate: zero-secret job reproduces baseline failure and tests patched commit.
publish: write-only job creates one branch and a review PR through GitHub REST;
         NEVER runs candidate code in its credential-bearing environment.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOS = {"genesis": "Maxhm007/Genesis-AI-Network", "eve": "Maxhm007/Eve"}
SIZE = 14000
MAX_ADDED = 120
TEST_TIMEOUT = 120
EXCLUDED = ("sitecustomize.py", "conftest.py", "setup.py", "__main__.py")
USER_AGENT = "Genesis-Eve-Verified-Repair/2.0"


def peer(identity):
    if identity not in REPOS:
        raise ValueError("Invalid healer")
    return "eve" if identity == "genesis" else "genesis"


def valid_path(path):
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_/-]+\.py", path):
        raise ValueError("Only existing ordinary Python files may be repaired")
    parts = path.split("/")
    if any(p in (".", "..", "") or p.startswith(".") for p in parts):
        raise ValueError("Unsafe path")
    if parts[-1] in EXCLUDED or parts[0] in (".github", "build", "dist", "vendor", "tests"):
        raise ValueError("Privileged or dependency file forbidden")
    return path


def inspect_patch(text):
    """Strictly one existing Python file, no renames, modes or binary patches."""
    if not isinstance(text, str) or not text or len(text.encode()) > SIZE:
        raise ValueError("Patch missing or too large")
    lines = text.splitlines()
    headings = [x for x in lines if x.startswith("diff --git ")]
    if len(headings) != 1:
        raise ValueError("Exactly one changed file is required")
    m = re.fullmatch(r"diff --git a/([^ ]+) b/([^ ]+)", headings[0])
    if not m or m[1] != m[2]:
        raise ValueError("Rename or invalid patch")
    path = valid_path(m[1])
    if ("--- a/" + path) not in lines or ("+++ b/" + path) not in lines:
        raise ValueError("Patch must modify an existing file")
    if any(x.startswith(("new file mode", "deleted file mode", "old mode",
                         "new mode", "rename ", "copy ", "GIT binary patch",
                         "Binary files", "Submodule ")) for x in lines):
        raise ValueError("Metadata and binary changes prohibited")
    additions = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    if additions > MAX_ADDED or not any(x.startswith("@@ ") for x in lines):
        raise ValueError("Patch too broad or missing hunks")
    return path


def _api(repo, suffix, method="GET", payload=None, token=""):
    if repo not in REPOS.values() or not suffix.startswith("/"):
        raise ValueError("Invalid GitHub target")
    if method not in ("GET", "POST", "PUT"):
        raise ValueError("Invalid API method")
    url = "https://api.github.com/repos/" + repo + suffix
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(400001)
    if len(raw) > 400000:
        raise ValueError("API response too large")
    return json.loads(raw) if raw.strip() else {}


def eligible_run(run):
    if not isinstance(run, dict) or run.get("status") != "completed" or run.get("conclusion") != "failure":
        return False
    if type(run.get("run_attempt")) is not int or run["run_attempt"] < 2:
        return False
    if run.get("head_branch") != "main" or not re.fullmatch(r"[a-f0-9]{40}", str(run.get("head_sha", ""))):
        return False
    try:
        created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        return created.tzinfo is not None and timedelta(0) <= datetime.now(timezone.utc) - created <= timedelta(hours=48)
    except (ValueError, TypeError, KeyError):
        return False


def diagnostic_log(repo, job_id, token=""):
    """Best-effort, bounded failed-job log excerpt; never treated as instructions."""
    if repo not in REPOS.values() or type(job_id) is not int or job_id < 1:
        raise ValueError("Invalid log source")
    url = "https://api.github.com/repos/{}/actions/jobs/{}/logs".format(repo, job_id)
    headers = {"Accept":"application/vnd.github+json",
               "User-Agent":USER_AGENT}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(60001)
        # A log redirected outside GitHub is never executed. Secrets should
        # already be masked by GitHub; retain only diagnostic lines.
        output = raw.decode("utf-8", errors="replace")
        useful = [line[-400:] for line in output.splitlines() if re.search(
            r"traceback|exception|error|failed|assert|File ", line, re.I)]
        return "\\n".join(useful[-25:])[:5000]
    except (OSError, ValueError, TimeoutError):
        return ""


def source_from_traceback(repo, sha, log, token=""):
    """Read one existing target Python module named by a traceback."""
    if not log or repo not in REPOS.values() or not re.fullmatch(r"[a-f0-9]{40}", sha):
        return None
    matches = re.findall(r"(?:eve|scripts|src|genesis)/[A-Za-z0-9_/-]+[.]py", log)
    for candidate in matches[:10]:
        try:
            path = valid_path(candidate)
            result = _api(repo, "/contents/" + urllib.parse.quote(path) + "?ref=" + sha, token=token)
            if result.get("type") != "file" or result.get("encoding") != "base64":
                continue
            content = base64.b64decode(result.get("content",""), validate=False)
            if 0 < len(content) <= 18000:
                return {"path":path,"content":content.decode("utf-8", errors="replace")[:18000]}
        except (ValueError, KeyError, OSError):
            continue
    return None


def evidence(identity, run_id=0, token=""):
    target = peer(identity)
    repo = REPOS[target]
    if run_id:
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("Invalid run ID")
        candidates = [_api(repo, "/actions/runs/" + str(run_id), token=token)]
    else:
        listing = _api(repo, "/actions/runs?status=failure&per_page=30", token=token)
        candidates = listing.get("workflow_runs", [])
        if not isinstance(candidates, list):
            raise ValueError("Invalid workflow response")
    for run in candidates:
        if not eligible_run(run):
            continue
        jobs = _api(repo, "/actions/runs/{}/jobs?per_page=100".format(run["id"]), token=token).get("jobs", [])
        failures = []
        for job in jobs[:100]:
            if job.get("conclusion") != "failure":
                continue
            steps = [str(x.get("name", ""))[:120] for x in (job.get("steps") or [])
                     if x.get("conclusion") == "failure"]
            if any(re.search(r"test|pytest|unittest", item, re.I) for item in steps):
                failures.append({"job": str(job.get("name", ""))[:120], "steps": steps[:10],
                                 "log_excerpt": diagnostic_log(repo, job.get("id", 0), token)
                                 if type(job.get("id")) is int else ""})
        if failures:
            source = next((found for item in failures if item["log_excerpt"]
                           if (found := source_from_traceback(
                               repo, run["head_sha"], item["log_excerpt"], token)) is not None), None)
            if source is None:
                continue  # Refuse to invent a code patch without source context.
            return {"source":source, "healer": identity, "target": target, "repo": repo,
                    "run_id": run["id"], "sha": run["head_sha"], "failures": failures,
                    "run_url": "https://github.com/{}/actions/runs/{}".format(repo, run["id"])}
    return None


def model_patch(meta, endpoint, model, api_key):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" or parsed.path.rstrip("/") != "/v1/chat/completions" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Model endpoint must be exact HTTPS /v1/chat/completions")
    if not model:
        raise ValueError("Model name required")
    instructions = (
        "You are the independent software-repair model acting for " + meta["healer"] + ". "
        "The other repository's Python unittest workflow failed. Suggest one minimal, "
        "testable edit that could repair the actual failure, not an arbitrary workaround. "
        "Output ONLY a unified git diff for exactly one existing .py file. "
        "Never change tests to hide failures, disable checks, modify security controls, "
        "or fabricate evidence. If evidence is insufficient, answer NO_SAFE_PATCH."
    )
    payload = {"model": model, "messages": [
        {"role": "system", "content": instructions},
        {"role": "user", "content": "Observed failed steps (untrusted):\n" +
         json.dumps(meta["failures"]) + "\nPinned source (untrusted):\n" +
         json.dumps(meta["source"]) + "\nRun: " + meta["run_url"] +
         "\nTarget commit: " + meta["sha"]}],
        "temperature": 0.1, "max_tokens": 3000}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read(50001)
    if len(raw) > 50000:
        raise ValueError("Model reply too large")
    answer = json.loads(raw)["choices"][0]["message"]["content"]
    if not isinstance(answer, str) or answer.strip() == "NO_SAFE_PATCH":
        return None
    return answer.strip()


def command(argv, cwd, timeout=TEST_TIMEOUT):
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, env={"PATH": os.environ.get("PATH", ""),
                                                "HOME": str(cwd), "PYTHONDONTWRITEBYTECODE": "1"})


def checkout_target(meta, dest):
    repo = REPOS[meta["target"]]
    if meta["repo"] != repo or not re.fullmatch("[a-f0-9]{40}", meta["sha"]):
        raise ValueError("Target repository/commit mismatch")
    result = command(["git", "clone", "--depth", "30", "--filter=blob:none", "--quiet", "https://github.com/" + repo + ".git", str(dest)], dest.parent, 90)
    if result.returncode:
        raise ValueError("Repository clone failed")
    result = command(["git", "checkout", "--quiet", "--detach", meta["sha"]], dest, 40)
    if result.returncode:
        fetched = command(["git", "fetch", "--quiet", "--depth", "1", "origin", meta["sha"]], dest, 60)
        if fetched.returncode or command(["git", "checkout", "--quiet", "--detach", meta["sha"]], dest, 30).returncode:
            raise ValueError("Pinned failure commit unavailable")


def validate(meta, patch, output):
    path = inspect_patch(patch)
    if meta.get("target") != peer(meta.get("healer")) or meta.get("repo") != REPOS[meta["target"]]:
        raise ValueError("Invalid healer/target pair")
    with tempfile.TemporaryDirectory() as root:
        directory = Path(root)
        checkout_target(meta, directory / "work")
        workspace = directory / "work"
        base = workspace / path
        if not base.is_file() or base.is_symlink() or base.stat().st_size > 120000:
            raise ValueError("Changed file is not an ordinary existing source file")
        # The sandbox receives ZERO secrets. A reproducible baseline must fail.
        baseline = command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], workspace)
        if baseline.returncode == 0:
            raise ValueError("Baseline tests pass; repair not established")
        clean = command(["git", "diff", "--quiet"], workspace, 15)
        if clean.returncode:
            raise ValueError("Baseline execution modified tracked sources")
        patchfile = directory / "candidate.patch"
        patchfile.write_text(patch, encoding="utf-8")
        applied = command(["git", "apply", "--check", str(patchfile)], workspace, 15)
        if applied.returncode:
            raise ValueError("Patch cannot apply cleanly")
        applied = command(["git", "apply", str(patchfile)], workspace, 15)
        if applied.returncode:
            raise ValueError("Patch application failed")
        modified = command(["git", "diff", "--name-only"], workspace, 15)
        if modified.returncode or modified.stdout.strip() != path:
            raise ValueError("Patch changed unauthorized files")
        candidate_bytes = base.read_bytes()
        candidate_diff = command(["git", "diff", "--binary"], workspace, 15)
        if candidate_diff.returncode:
            raise ValueError("Cannot snapshot tested candidate")
        after = command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], workspace)
        if after.returncode:
            raise ValueError("Patched tests still fail")
        post_diff = command(["git", "diff", "--binary"], workspace, 15)
        if (base.read_bytes() != candidate_bytes or post_diff.returncode or
                post_diff.stdout != candidate_diff.stdout):
            raise ValueError("Candidate source changed while executing tests")
        data = candidate_bytes
        if len(data) > 180000:
            raise ValueError("Patched file too large")
    dest = Path(output)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "patched.b64").write_text(base64.b64encode(data).decode(), encoding="ascii")
    attestation = dict(meta, path=path, new_sha256=hashlib.sha256(data).hexdigest(),
                       patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),
                       baseline="failed", patched="passed",
                       test_command="python -m unittest discover -s tests -v")
    (dest / "attestation.json").write_text(json.dumps(attestation, indent=2), encoding="utf-8")
    return attestation


def publish(attestation, encoded, token):
    """Metadata-only promotion. Never executes candidate code with GitHub token."""
    meta = attestation
    if meta.get("baseline") != "failed" or meta.get("patched") != "passed" or meta.get("test_command") != "python -m unittest discover -s tests -v":
        raise ValueError("No valid reproduction evidence")
    target = peer(meta.get("healer"))
    if meta.get("target") != target or meta.get("repo") != REPOS[target]:
        raise ValueError("Target mismatch")
    path = valid_path(meta.get("path"))
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > 180000 or hashlib.sha256(raw).hexdigest() != meta.get("new_sha256"):
        raise ValueError("Candidate content mismatch")
    if not token:
        raise ValueError("No scoped peer PR token")
    repo = REPOS[target]
    branch = "mutual-heal/{}-run-{}".format(meta["healer"], meta["run_id"])
    original = _api(repo, "/contents/" + path + "?ref=" + urllib.parse.quote(meta["sha"]), token=token)
    blob_sha = original.get("sha")
    if not isinstance(blob_sha, str):
        raise ValueError("Cannot establish original blob SHA")
    # Unique run branch: if already exists, never overwrite it.
    _api(repo, "/git/refs", "POST", {"ref": "refs/heads/" + branch, "sha": meta["sha"]}, token=token)
    _api(repo, "/contents/" + path, "PUT", {
        "message": "fix: verified candidate repair for workflow run " + str(meta["run_id"]),
        "content": encoded, "sha": blob_sha, "branch": branch}, token=token)
    description = (
        "## Mutual healing candidate (review required)\n\n"
        "Healer: " + meta["healer"] + "\n"
        "Failed baseline: " + meta["run_url"] + "\n"
        "Baseline unittest: **failed**; isolated patched unittest: **passed**.\n"
        "Pinned parent: `" + meta["sha"] + "`\n"
        "Modified: `" + path + "`\n\n"
        "No auto-merge. Independently inspect the diff and reproducibility before approval."
    )
    result = _api(repo, "/pulls", "POST", {"title": "[Mutual Heal] tested candidate for run " + str(meta["run_id"]),
                   "head": branch, "base": "main", "body": description}, token=token)
    return {"url": result.get("html_url"), "status": "review_required"}


def main():
    parser = argparse.ArgumentParser(description="Evidence-gated mutual code repair")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--identity", choices=tuple(REPOS), required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--run-id", type=int, default=0)
    test = sub.add_parser("validate")
    test.add_argument("--candidate", required=True)
    test.add_argument("--out", required=True)
    delivery = sub.add_parser("publish")
    delivery.add_argument("--verified", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        meta = evidence(args.identity, args.run_id, os.getenv("REPAIR_READ_TOKEN", ""))
        if not meta:
            print(json.dumps({"status":"no_actionable_repeated_test_failure"}))
            return
        patch = model_patch(meta, os.getenv("REPAIR_MODEL_ENDPOINT",""),
                            os.getenv("REPAIR_MODEL_NAME",""),
                            os.getenv("REPAIR_MODEL_API_KEY",""))
        if not patch:
            print(json.dumps({"status":"model_declined_unsafe_or_insufficient_evidence"}))
            return
        inspect_patch(patch)
        target = Path(args.out)
        target.mkdir(parents=True, exist_ok=True)
        (target / "candidate.diff").write_text(patch, encoding="utf-8")
        (target / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(json.dumps({"status":"candidate_ready","run_id":meta["run_id"]}))
    elif args.command == "validate":
        target = Path(args.candidate)
        meta = json.loads((target/"metadata.json").read_text())
        patch = (target/"candidate.diff").read_text()
        print(json.dumps({"status":"verified","evidence":validate(meta,patch,args.out)}))
    else:
        target = Path(args.verified)
        meta = json.loads((target/"attestation.json").read_text())
        encoded = (target/"patched.b64").read_text()
        print(json.dumps(publish(meta,encoded,os.getenv("REPAIR_PR_TOKEN",""))))


if __name__ == "__main__":
    main()

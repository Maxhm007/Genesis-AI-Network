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
import secrets
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
    # GitHub traceback paths may identify approved root-level Python modules
    # without an "eve/" or "src/" prefix. These two exact basenames are
    # allowed; arbitrary external traceback paths remain excluded.
    matches = re.findall(
        r"(?:eve|scripts|src|genesis)/[A-Za-z0-9_/-]+[.]py"
        r"|(?<=/)(?:mutual_healer|repair_v2)[.]py",
        log,
    )
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



def deterministic_patch(meta):
    """Bounded zero-model hypothesis: one observed int/bool equality mismatch.

    This is NOT general AI code repair. Never obey diagnostic log instructions;
    treat text only as evidence of a narrow Python assertion mismatch. The
    separate secret-free job must still reproduce baseline failure and verify
    the exact patched suite before a human-reviewed PR may be published.
    """
    import ast
    import difflib

    source = meta.get("source") or {}
    path = valid_path(source.get("path"))
    code = source.get("content")
    failures = meta.get("failures") or []
    if not isinstance(code, str) or len(code.encode("utf-8")) > 18000:
        return None
    if not isinstance(failures, list):
        return None
    logs = "\n".join(str(item.get("log_excerpt", ""))[:5000]
                     for item in failures[:10] if isinstance(item, dict))
    # pytest: "assert 1 == 2"; unittest: "AssertionError: 1 != 2".
    token = r"(?:True|False|[0-9]{1,6})"
    pytest_match = re.findall(r"\bassert\s+(" + token + r")\s*==\s*(" + token + r")\b", logs)
    unittest_match = re.findall(r"AssertionError:\s*(" + token + r")\s*!=\s*(" + token + r")\b", logs)
    evidence_pairs = set(pytest_match + unittest_match)
    if len(evidence_pairs) != 1:
        return None
    observed, expected = next(iter(evidence_pairs))
    if observed == expected:
        return None
    def literal(value):
        if value == "True": return True
        if value == "False": return False
        return int(value)

    actual_value, desired_value = literal(observed), literal(expected)
    if type(actual_value) is not type(desired_value):
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    candidates = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and type(node.value.value) is type(actual_value)
        and node.value.value == actual_value
    ]
    if len(candidates) != 1:
        return None
    lines = code.splitlines(keepends=True)
    index = candidates[0].lineno - 1
    if not 0 <= index < len(lines):
        return None
    before = lines[index]
    # Only change a complete, simple return literal statement, not an
    # expression, annotation, comment, conditional, or malicious payload.
    m = re.fullmatch(r"([ \t]*return[ \t]+)" + re.escape(observed) +
                     r"([ \t]*(?:#[^\r\n]*)?\r?\n?)", before)
    if not m:
        return None
    proposed = lines.copy()
    proposed[index] = m.group(1) + repr(desired_value) + m.group(2)
    after_code = "".join(proposed)
    enforce_literal_return_repair(code.encode("utf-8"), after_code.encode("utf-8"))
    records = list(difflib.unified_diff(
        lines, proposed, fromfile="a/" + path, tofile="b/" + path))
    # The original source may omit the final newline. Git requires an
    # explicit marker after each affected unterminated diff record.
    unified = "".join(item if item.endswith("\n") else
                      item + "\n\\ No newline at end of file\n"
                      for item in records)
    diff = "diff --git a/{0} b/{0}\n".format(path) + unified
    inspect_patch(diff)
    return diff

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
    return answer if answer.endswith("\n") else answer + "\n"


def command(argv, cwd, timeout=TEST_TIMEOUT):
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, env={"PATH": os.environ.get("PATH", ""),
                                                "HOME": str(cwd), "PYTHONDONTWRITEBYTECODE": "1"})



# This trusted runner reports completion only AFTER the unittest suite returns.
# An imported module calling os._exit(0) can no longer masquerade as a passing suite.
TEST_HARNESS = """
import json
import sys
import unittest

nonce = sys.argv[1]
suite = unittest.defaultTestLoader.discover("tests")
discovered = suite.countTestCases()
if discovered < 1:
    sys.exit(3)
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.stdout.write(chr(10))
print("__MUTUAL_HEAL_SUITE_FINISHED__" + nonce + ":" +
      json.dumps({"discovered": discovered, "executed": result.testsRun,
                  "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "successful": result.wasSuccessful()}),
      flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
"""



# Genesis' native test suite includes pytest functions, not just TestCase classes.
# The harness must execute the real collector or it cannot certify repairs.
PYTEST_HARNESS = """
import json
import sys
import pytest

nonce = sys.argv[1]
class Audit:
    def __init__(self):
        self.seen = set()
        self.failures = 0
        self.errors = 0
        self.skipped = 0
        self.collection_skips = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed or report.skipped:
            self.seen.add(report.nodeid)
        if report.failed:
            if report.when == "call":
                self.failures += 1
            else:
                self.errors += 1
        if report.skipped:
            self.skipped += 1

    def pytest_collectreport(self, report):
        # Import/collection failures are reproducible baseline errors,
        # even when no test function could execute.
        if report.failed:
            self.errors += 1
        if report.skipped:
            self.skipped += 1
            self.collection_skips += 1

    def pytest_sessionfinish(self, session, exitstatus):
        discovered = session.testscollected
        executed = len(self.seen)
        self.errors += session.config.pluginmanager.get_plugin(
            "terminalreporter")._numcollected == 0 if False else 0
        passed = exitstatus == 0 and discovered > 0 and executed == discovered
        print(chr(10) + "__MUTUAL_HEAL_SUITE_FINISHED__" + nonce + ":" +
              json.dumps({"discovered": discovered, "executed": executed,
                          "failures": self.failures,
                          "errors": self.errors,
                          "skipped": self.skipped,
                          "collection_skips": self.collection_skips,
                          "successful": passed}), flush=True)

audit = Audit()
code = pytest.main(["-q", "tests"], plugins=[audit])
sys.exit(code)
"""


def _is_pytest_repository(workspace):
    # The target's checked-out, pinned requirements declare pytest.
    # Eve uses stdlib unittest only; keep its existing tracked runner.
    requirements = workspace / "requirements.txt"
    if not requirements.is_file():
        return False
    return any(line.strip().lower().startswith("pytest") for line in
               requirements.read_text(encoding="utf-8").splitlines())

def run_tracked_tests(workspace):
    nonce = secrets.token_hex(16)
    harness = PYTEST_HARNESS if _is_pytest_repository(workspace) else TEST_HARNESS
    result = command([sys.executable, "-c", harness, nonce], workspace)
    prefix = "__MUTUAL_HEAL_SUITE_FINISHED__" + nonce + ":"
    markers = [line[len(prefix):] for line in result.stdout.splitlines()
               if line.startswith(prefix)]
    if len(markers) != 1:
        raise ValueError("Test suite did not complete; refusing unverified result")
    try:
        stats = json.loads(markers[0])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid test completion record") from exc
    if (not isinstance(stats, dict) or
            type(stats.get("discovered")) is not int or
            type(stats.get("executed")) is not int or
            (stats["discovered"] < 1 and (stats["successful"] or stats["errors"] < 1)) or
            stats["executed"] > stats["discovered"] or
            (stats["successful"] and stats["executed"] != stats["discovered"]) or
            (not stats["successful"] and stats["executed"] < stats["discovered"] and
             (type(stats.get("errors")) is not int or stats["errors"] < 1)) or
            type(stats.get("failures")) is not int or
            type(stats.get("errors")) is not int or
            type(stats.get("successful")) is not bool):
        raise ValueError("Test suite execution incomplete or invalid")
    if stats["successful"] != (result.returncode == 0):
        raise ValueError("Test status contradicts completion record")
    if stats["successful"] and (stats["failures"] or stats["errors"]):
        raise ValueError("Passing suite contains failures")
    return result, stats



def _parse_execution_equivalent_source(source):
    """Accept only UTF-8 Python source interpreted identically by byte/text parsers.

    Python's PEP 263 encoding declarations can transform comment bytes into
    executable code (e.g. coding: unicode_escape). Reject encoding cookies,
    BOMs and non-UTF-8 input before AST comparison. This is deliberately
    conservative for untrusted model-authored fixes.
    """
    import ast
    import io
    import tokenize

    if not isinstance(source, bytes) or not source or source.startswith(bytes.fromhex("efbbbf")):
        raise ValueError("Restricted auto-repair requires plain UTF-8 source without BOM")
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
        if encoding.lower().replace("_", "-") != "utf-8":
            raise ValueError("Restricted auto-repair rejects non-UTF-8 source encoding")
        # Reject all PEP 263 declarations, including UTF-8 cookies. Otherwise
        # an apparently harmless comment change could alter execution semantics.
        cookie = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*[-_.a-zA-Z0-9]+")
        if any(cookie.match(line) for line in source.splitlines()[:2]):
            raise ValueError("Restricted auto-repair forbids source encoding declarations")
        decoded = source.decode("utf-8", errors="strict")
        byte_tree = ast.parse(source, mode="exec")
        text_tree = ast.parse(decoded, mode="exec")
        if ast.dump(byte_tree, include_attributes=False) != ast.dump(text_tree, include_attributes=False):
            raise ValueError("Source parses differently from Python execution")
        return byte_tree
    except (SyntaxError, UnicodeError, LookupError, tokenize.TokenError) as exc:
        raise ValueError("Restricted auto-repair requires valid UTF-8 Python") from exc


def enforce_literal_return_repair(before, after):
    """Only 1–4 literal return changes in equivalent UTF-8 Python source.

    A candidate can otherwise forge in-process unittest success evidence.
    The exact same guard runs in both the test job and PR publisher.
    """
    import ast
    old_tree = _parse_execution_equivalent_source(before)
    new_tree = _parse_execution_equivalent_source(after)
    changes = 0

    def compare(old, new, parent=None, field=None):
        nonlocal changes
        if type(old) is not type(new):
            raise ValueError("Restricted auto-repair: executable structure changed")
        if isinstance(old, ast.Constant):
            if old.value != new.value:
                if (parent != "Return" or field != "value" or
                        type(old.value) is not type(new.value) or
                        type(old.value) not in (int, float, bool, str)):
                    raise ValueError("Restricted auto-repair: only return literals may change")
                changes += 1
            return
        if isinstance(old, ast.AST):
            for name in old._fields:
                compare(getattr(old, name), getattr(new, name), type(old).__name__, name)
        elif isinstance(old, (list, tuple)):
            if len(old) != len(new):
                raise ValueError("Restricted auto-repair: statement count changed")
            for a, b in zip(old, new):
                compare(a, b, parent, field)
        elif old != new:
            raise ValueError("Restricted auto-repair: nonliteral changes forbidden")

    compare(old_tree, new_tree)
    if not 1 <= changes <= 4:
        raise ValueError("Restricted auto-repair: expected 1-4 safe return literals")
    return changes

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
        runner = ("python -m pytest -q tests" if _is_pytest_repository(workspace)
                  else "python -m unittest discover -s tests -v")
        base = workspace / path
        if not base.is_file() or base.is_symlink() or base.stat().st_size > 120000:
            raise ValueError("Changed file is not an ordinary existing source file")
        base_original = base.read_bytes()
        # The sandbox receives ZERO secrets. A reproducible baseline must fail.
        baseline, baseline_stats = run_tracked_tests(workspace)
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
        enforce_literal_return_repair(base_original, candidate_bytes)
        candidate_diff = command(["git", "diff", "--binary"], workspace, 15)
        if candidate_diff.returncode:
            raise ValueError("Cannot snapshot tested candidate")
        after, after_stats = run_tracked_tests(workspace)
        if after.returncode:
            raise ValueError("Patched tests still fail")
        if after_stats["executed"] < baseline_stats["executed"]:
            raise ValueError("Patched test coverage fell below the baseline")
        if after_stats.get("collection_skips", 0) > baseline_stats.get("collection_skips", 0):
            raise ValueError("Patched suite skipped additional test modules during collection")
        if (after_stats["skipped"] > baseline_stats["skipped"] and not
                (baseline_stats["errors"] > 0 and
                 after_stats["discovered"] > baseline_stats["discovered"])):
            raise ValueError("Patched test suite skipped additional tests")
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
                       tests_completed=True, tests_executed=after_stats["executed"],
                       test_command=runner)
    (dest / "attestation.json").write_text(json.dumps(attestation, indent=2), encoding="utf-8")
    return attestation


def publish(attestation, encoded, token):
    """Metadata-only promotion. Never executes candidate code with GitHub token."""
    meta = attestation
    if (meta.get("baseline") != "failed" or meta.get("patched") != "passed" or
            meta.get("test_command") not in (
                "python -m unittest discover -s tests -v", "python -m pytest -q tests") or
            meta.get("tests_completed") is not True or
            type(meta.get("tests_executed")) is not int or meta["tests_executed"] < 1):
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
    if original.get("encoding") != "base64" or not isinstance(original.get("content"), str):
        raise ValueError("Missing original source for independent publication gate")
    baseline_source = base64.b64decode(original["content"])
    enforce_literal_return_repair(baseline_source, raw)
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
        "Test runner: `" + meta["test_command"] + "`\n"
        "Baseline tests: **failed**; isolated patched tests: **passed**.\n"
        "Pinned parent: `" + meta["sha"] + "`\n"
        "Modified: `" + path + "`\n\n"
        "No auto-merge. Independently inspect the diff and reproducibility before approval."
    )
    result = _api(repo, "/pulls", "POST", {"title": "[Mutual Heal] tested candidate for run " + str(meta["run_id"]),
                   "head": branch, "base": "main", "body": description}, token=token)
    return {"url": result.get("html_url"), "status": "review_required"}


def main():
    parser = argparse.ArgumentParser(description="Evidence-gated mutual code repair")
    parser.add_argument("--local", action="store_true", help="Use only the current repository GITHUB_TOKEN; refuse remote-target credentials")
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
        if args.local and os.getenv("GITHUB_REPOSITORY") != REPOS[peer(args.identity)]:
            raise ValueError("Local repair identity must target the current repository")
        meta = evidence(args.identity, args.run_id,
                        os.getenv("GITHUB_TOKEN", "") if args.local else os.getenv("REPAIR_READ_TOKEN", ""))
        if not meta:
            print(json.dumps({"status":"no_actionable_repeated_test_failure"}))
            return
        endpoint, model = os.getenv("REPAIR_MODEL_ENDPOINT", ""), os.getenv("REPAIR_MODEL_NAME", "")
        if endpoint and model:
            patch = model_patch(meta, endpoint, model, os.getenv("REPAIR_MODEL_API_KEY", ""))
        else:
            patch = deterministic_patch(meta)
        if not patch:
            print(json.dumps({"status":"no_safe_candidate_from_evidence"}))
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
        if args.local and (meta.get("target") not in REPOS or
                           os.getenv("GITHUB_REPOSITORY") != REPOS[meta["target"]]):
            raise ValueError("Local PR publication refuses a foreign repository")
        token = os.getenv("GITHUB_TOKEN", "") if args.local else os.getenv("REPAIR_PR_TOKEN", "")
        print(json.dumps(publish(meta,encoded,token)))


if __name__ == "__main__":
    main()

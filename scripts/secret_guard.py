from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


MAX_BLOB_BYTES = 2_000_000

# Keep signatures split where useful so the scanner does not detect its own
# pattern source as a credential.
PRIVATE_KEY_MARKER = "-----BEGIN " + "PRIVATE KEY-----"
RSA_PRIVATE_KEY_MARKER = "-----BEGIN RSA " + "PRIVATE KEY-----"
EC_PRIVATE_KEY_MARKER = "-----BEGIN EC " + "PRIVATE KEY-----"
OPENSSH_PRIVATE_KEY_MARKER = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile("|".join(re.escape(value) for value in (
        PRIVATE_KEY_MARKER,
        RSA_PRIVATE_KEY_MARKER,
        EC_PRIVATE_KEY_MARKER,
        OPENSSH_PRIVATE_KEY_MARKER,
    )))),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,255}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,255}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("stripe_live_secret", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b")),
    ("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
)

RISKY_BASENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "service-account.json",
    "service_account.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
RISKY_SUFFIXES = {".pem", ".p12", ".pfx"}
# `.key` is commonly a private key but can also be harmless source/test data.
# Treat it as risky unless it is clearly documentation/example material.


@dataclass(frozen=True)
class Finding:
    kind: str
    location: str
    detail: str


def run_git(*args: str, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    return proc.stdout


def looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def risky_name(path: str) -> str | None:
    p = Path(path)
    low = p.name.lower()
    if low in RISKY_BASENAMES:
        return "risky_secret_filename"
    if p.suffix.lower() in RISKY_SUFFIXES:
        return "risky_secret_filename"
    if p.suffix.lower() == ".key":
        normalized = path.lower()
        if not any(token in normalized for token in ("example", "sample", "fixture", "test", "docs/")):
            return "risky_secret_filename"
    return None


def scan_text(data: bytes, location: str) -> list[Finding]:
    if len(data) > MAX_BLOB_BYTES or looks_binary(data):
        return []
    text = data.decode("utf-8", errors="ignore")
    findings: list[Finding] = []
    for kind, pattern in PATTERNS:
        if pattern.search(text):
            findings.append(Finding(kind, location, "credential-like content detected; value redacted"))
    return findings


def tracked_files() -> list[str]:
    raw = run_git("ls-files", "-z")
    return [item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\x00") if item]


def scan_worktree() -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_files():
        name_issue = risky_name(path)
        if name_issue:
            findings.append(Finding(name_issue, path, "secret-bearing filename is tracked"))
        p = Path(path)
        if p.is_file() and p.stat().st_size <= MAX_BLOB_BYTES:
            findings.extend(scan_text(p.read_bytes(), path))
    return findings


def history_objects() -> list[tuple[str, str]]:
    """Return unique reachable blob-ish object ids and their last observed path.

    Object type is checked before reading, so commits/trees are ignored. The
    repository is intentionally small; this favors correctness and no external
    dependencies over clever batching.
    """
    raw = run_git("rev-list", "--objects", "--all").decode("utf-8", errors="replace")
    seen: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        sha, _, path = line.partition(" ")
        if sha and sha not in seen:
            seen[sha] = path
    return list(seen.items())


def scan_history() -> list[Finding]:
    findings: list[Finding] = []
    for sha, path in history_objects():
        obj_type = run_git("cat-file", "-t", sha).decode().strip()
        if obj_type != "blob":
            continue
        size = int(run_git("cat-file", "-s", sha).decode().strip())
        if size > MAX_BLOB_BYTES:
            continue
        label = f"history:{sha[:12]}:{path or '<unknown>'}"
        if path:
            name_issue = risky_name(path)
            if name_issue:
                findings.append(Finding(name_issue, label, "secret-bearing filename exists in reachable Git history"))
        data = run_git("cat-file", "blob", sha)
        findings.extend(scan_text(data, label))
    return findings


def deduplicate(findings: list[Finding]) -> list[Finding]:
    unique: dict[tuple[str, str], Finding] = {}
    for finding in findings:
        unique[(finding.kind, finding.location)] = finding
    return sorted(unique.values(), key=lambda item: (item.kind, item.location))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Genesis tracked files and Git history for likely secrets.")
    parser.add_argument("--history", action="store_true", help="also scan every reachable Git blob")
    args = parser.parse_args()

    findings = scan_worktree()
    if args.history:
        findings.extend(scan_history())
    findings = deduplicate(findings)

    if findings:
        print(f"GENESIS_SECRET_GUARD=FAIL findings={len(findings)}")
        for finding in findings:
            print(f"- {finding.kind}: {finding.location} — {finding.detail}")
        print("Rotate/revoke any real credential before rewriting history.")
        return 1

    scope = "worktree+history" if args.history else "worktree"
    print(f"GENESIS_SECRET_GUARD=PASS scope={scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

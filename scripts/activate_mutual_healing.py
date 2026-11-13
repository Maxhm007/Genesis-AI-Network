#!/usr/bin/env python3
"""One-time LOCAL activation of Genesis <-> Eve GitHub recovery watchdogs.

Run on your own machine after installing and authenticating GitHub CLI:
  gh auth login
  python scripts/activate_mutual_healing.py

This script does not create tokens, log them, save them to disk, or touch AI
repair activation. Create separate fine-grained PATs through GitHub UI first.
"""
from __future__ import annotations

import getpass
import json
import shutil
import subprocess
import sys
import warnings

GENESIS = "Maxhm007/Genesis-AI-Network"
EVE = "Maxhm007/Eve"

CONFIGS = (
    (GENESIS, EVE, "heal-eve.yml"),
    (EVE, GENESIS, "heal-genesis.yml"),
)


def gh(*args, secret=None):
    """Do not pass secrets in argv: pipe via stdin to GitHub CLI."""
    command = ["gh", *args]
    proc = subprocess.run(
        command, input=(secret + "\n") if secret is not None else None,
        text=True, capture_output=True, timeout=90,
    )
    if proc.returncode != 0:
        error = proc.stderr.strip() or "GitHub CLI operation failed"
        # GitHub CLI error output can include entered data in unexpected cases;
        # replace secret before displaying anything.
        if secret:
            error = error.replace(secret, "[REDACTED]")
        raise RuntimeError(f"GitHub command failed: {' '.join(command)}: {error}")
    return proc.stdout.strip()


def setup():
    if not shutil.which("gh"):
        raise RuntimeError("Install GitHub CLI: https://cli.github.com/")
    gh("auth", "status")
    print("Reciprocal watchdog activation (NOT AI code repair).")
    print("Create TWO different fine-grained GitHub tokens first:")
    print("  (1) restricted to Eve: Actions and Issues read/write")
    print("  (2) restricted to Genesis: Actions and Issues read/write")
    print("  Metadata read must also be allowed.")
    print("Never share or commit the token values.\n")
    approval = input("Type ACTIVATE to configure both repositories: ").strip()
    if approval != "ACTIVATE":
        print("Cancelled. Nothing changed.")
        return 1

    # Prompt for both secrets BEFORE activating either repository.
    tokens = []
    try:
        for origin, destination, _ in CONFIGS:
            prompt = f"Fine-grained token for {destination}, stored ONLY in {origin}: "
            try:
                # Python getpass can otherwise fall back to echoing secrets in
                # unsupported IDE consoles, which is NEVER acceptable here.
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    value = getpass.getpass(prompt)
            except getpass.GetPassWarning as exc:
                raise RuntimeError(
                    "Private token input unavailable. Run in a secure terminal."
                ) from exc
            if not value:
                raise ValueError("Missing peer token")
            if any(value == previous for previous in tokens):
                raise ValueError("Each direction requires a DIFFERENT peer token")
            tokens.append(value)

        for (origin, destination, workflow), token in zip(CONFIGS, tokens):
            print(f"Configuring {origin} -> {destination}...")
            gh("secret", "set", "PEER_HEAL_TOKEN", "--repo", origin, secret=token)
            gh("variable", "set", "MUTUAL_HEAL_ENABLED", "--repo", origin, "--body", "true")
            gh("workflow", "enable", workflow, "--repo", origin)

        for origin, destination, workflow in CONFIGS:
            print(f"Dispatching {origin} -> {destination}...")
            gh("workflow", "run", workflow, "--repo", origin, "--ref", "main")

        print("\nWatchdogs DISPATCHED, not yet verified recovered.")
        print("Inspect job logs and confirm peer API access:")
        for origin, _, workflow in CONFIGS:
            print(f"  https://github.com/{origin}/actions/workflows/{workflow}")
        print("AI-generated repairs remain gated (MUTUAL_HEAL_REPAIR_ENABLED untouched).")
        return 0
    finally:
        # Best-effort drop references promptly; no secrets printed or persisted.
        tokens.clear()


if __name__ == "__main__":
    try:
        sys.exit(setup())
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Activation stopped: {exc}", file=sys.stderr)
        sys.exit(1)

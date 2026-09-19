from __future__ import annotations

import argparse
import re
import sys


TARGET_PATTERNS = (
    re.compile(r"^-\s*\*\*Target:\*\*\s*`([^`\n]+)`\s*$", re.MULTILINE),
    re.compile(r"^Target:\s*`([^`\n]+)`\s*$", re.MULTILINE),
)


def extract_issue_target(body: str) -> str:
    """Return the explicit repository target from supported Genesis Issue formats."""
    text = str(body or "")
    for pattern in TARGET_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip().replace("\\", "/")
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the explicit target from a Genesis GitHub Issue body")
    parser.add_argument("--body", default=None)
    args = parser.parse_args()
    body = args.body if args.body is not None else sys.stdin.read()
    print(extract_issue_target(body))


if __name__ == "__main__":
    main()

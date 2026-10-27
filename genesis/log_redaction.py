"""Remove credentials from command output before it is stored or published.

Test and tool output can end up in issue comments and uploaded artifacts,
which GitHub does not mask. Everything that persists such output should pass
it through ``redact_secrets`` first.
"""

from __future__ import annotations

import os
import re

_SECRET_NAME = r"[A-Za-z0-9_-]*(?:secret|token|password|passwd|api[_-]?key|private[_-]?key)[A-Za-z0-9_-]*"

_PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"(?i)(authorization:\s*(?:bearer|token|basic)\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{12,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s:/@]+:[^\s@/]+@"), r"\1[REDACTED]@"),
    # JSON or quoted keys: "token": "value"
    (re.compile(r"(?i)([\"']" + _SECRET_NAME + r"[\"']\s*:\s*[\"'])(?!\d+[\"'])[^\"']{4,}([\"'])"), r"\1[REDACTED]\2"),
    # key=value; plain numbers such as max_tokens=1000 are settings, not secrets.
    (re.compile(r"(?i)\b(" + _SECRET_NAME + r")\s*[=:]\s*['\"]?(?!\d+\b)[^\s'\"]{4,}"), r"\1=[REDACTED]"),
)

# Environment variables whose live values must never appear in output.
_SENSITIVE_ENV_RE = re.compile(r"(?i)(secret|token|password|passwd|api[_-]?key|private[_-]?key)")


def redact_secrets(text: object, *, environ: dict[str, str] | None = None) -> str:
    value = str(text or "")
    env = os.environ if environ is None else environ
    for name, secret in env.items():
        if secret and len(secret) >= 8 and _SENSITIVE_ENV_RE.search(name):
            value = value.replace(secret, "[REDACTED]")
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value

"""Decide which issue comments Genesis may act on.

Genesis-AI-Network is public, so anyone can comment on its issues. Status,
evidence and repair-memory comments steer what the solver writes and when an
issue closes, so only comments from Genesis's own automation (and, where a
caller allows it, the repository's maintainers) may be trusted.
"""

from __future__ import annotations

import os

DEFAULT_AUTOMATION_LOGINS = frozenset({"github-actions[bot]"})
MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def automation_logins() -> frozenset[str]:
    extra = os.environ.get("GENESIS_TRUSTED_COMMENT_AUTHORS", "")
    names = {name.strip().lower() for name in extra.split(",") if name.strip()}
    return frozenset({login.lower() for login in DEFAULT_AUTOMATION_LOGINS} | names)


def _login(row: dict) -> str:
    user = row.get("user")
    return str(user.get("login") or "").lower() if isinstance(user, dict) else ""


def _is_bot_account(row: dict) -> bool:
    user = row.get("user")
    return isinstance(user, dict) and str(user.get("type") or "") == "Bot"


def is_automation_comment(row: object) -> bool:
    return isinstance(row, dict) and _is_bot_account(row) and _login(row) in automation_logins()


def is_trusted_comment(row: object, *, allow_maintainers: bool = True) -> bool:
    if not isinstance(row, dict):
        return False
    if is_automation_comment(row):
        return True
    if allow_maintainers:
        return str(row.get("author_association") or "").upper() in MAINTAINER_ASSOCIATIONS
    return False


def trusted_comments(rows: list[dict] | None, *, allow_maintainers: bool = True) -> list[dict]:
    return [row for row in rows or [] if is_trusted_comment(row, allow_maintainers=allow_maintainers)]

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

SOURCES: tuple[str, ...] = (
    "huggingface/transformers",
    "vllm-project/vllm",
    "microsoft/autogen",
    "microsoft/semantic-kernel",
    "ggml-org/llama.cpp",
    "langchain-ai/langgraph",
)

RECENT_DAYS = 30
MAX_RELEASES_PER_SOURCE = 8
MIN_RELEVANCE_SCORE = 6

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "the", "to", "via", "with", "support", "supports",
    "add", "adds", "added", "adding", "new", "enable", "enables", "enabled", "implement",
    "implements", "implemented", "integration", "integrate", "fix", "fixes", "update",
    "updates", "release", "model", "models", "api", "feature", "features",
}

RELEVANCE_WEIGHTS: dict[str, int] = {
    "agent": 5,
    "agentic": 5,
    "computer use": 6,
    "gui": 5,
    "reasoning": 5,
    "verification": 4,
    "verifier": 4,
    "self-verification": 6,
    "memory": 5,
    "long context": 5,
    "long-context": 5,
    "context": 2,
    "tool use": 5,
    "tool-use": 5,
    "tool calling": 5,
    "function calling": 5,
    "planning": 4,
    "retrieval": 4,
    "reranking": 3,
    "multimodal": 5,
    "vision": 4,
    "video": 4,
    "audio": 4,
    "speech": 4,
    "coding": 4,
    "code repair": 5,
    "self-improvement": 6,
    "self improvement": 6,
    "continual learning": 5,
    "continuous learning": 5,
    "online learning": 5,
    "on-device": 5,
    "on device": 5,
    "edge": 4,
    "distributed": 3,
    "decentralized": 5,
    "speculative": 3,
    "kv cache": 2,
    "quantization": 2,
    "structured output": 4,
    "structured outputs": 4,
}

CORE_NEEDS = {
    "agent", "agentic", "computer use", "gui", "reasoning", "verification", "verifier",
    "memory", "long context", "long-context", "tool use", "tool-use", "tool calling",
    "function calling", "planning", "retrieval", "multimodal", "vision", "video", "audio",
    "speech", "coding", "code repair", "self-improvement", "self improvement",
    "continual learning", "continuous learning", "online learning", "on-device",
    "on device", "edge", "distributed", "decentralized", "structured output",
    "structured outputs",
}

ACTION_HINTS = (
    "add ", "adds ", "added ", "support ", "supports ", "introduce ", "introduces ",
    "enable ", "enables ", "implement ", "implements ", "integration", "new ",
)


@dataclass(frozen=True)
class Candidate:
    source_repo: str
    release_name: str
    published_at: str
    source_url: str
    statement: str
    capability_name: str
    fingerprint: str
    score: int
    matched_needs: tuple[str, ...]


def _request_json(url: str, token: str | None = None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Genesis-AI-Network/capability-discovery",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str) -> object:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Genesis-AI-Network/capability-discovery",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.+-]{2,}", value.lower())
        if token not in STOPWORDS and not token.isdigit()
    }


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _relevance(statement: str) -> tuple[int, tuple[str, ...]]:
    lower = statement.lower()
    score = 0
    matched: list[str] = []
    for keyword, weight in RELEVANCE_WEIGHTS.items():
        if keyword in lower:
            score += weight
            if keyword in CORE_NEEDS:
                matched.append(keyword)
    return score, tuple(dict.fromkeys(matched))


def _clean_statement(line: str) -> str:
    value = re.sub(r"^\s*[-*+]\s*", "", line)
    value = re.sub(r"^\s*\d+[.)]\s*", "", value)
    value = re.sub(r"\s+by\s+@\S+.*$", "", value, flags=re.I)
    value = re.sub(r"\s*\(#\d+\)\s*$", "", value)
    value = re.sub(r"https?://\S+", "", value)
    return _normalize_space(value).strip(" -:;.")


def _capability_name(statement: str) -> str:
    value = re.sub(
        r"^(?:add(?:s|ed|ing)?|support(?:s|ed|ing)?|introduce(?:s|d|ing)?|"
        r"enable(?:s|d|ing)?|implement(?:s|ed|ing)?|integrat(?:e|es|ed|ing))\s+",
        "",
        statement,
        flags=re.I,
    )
    value = re.sub(r"\s+\([^)]*#\d+[^)]*\)\s*$", "", value)
    value = _normalize_space(value)
    if len(value) > 120:
        value = value[:117].rstrip() + "..."
    return value


def _fingerprint(capability_name: str) -> str:
    canonical = " ".join(sorted(_tokens(capability_name)))
    if not canonical:
        canonical = capability_name.lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def extract_candidates(
    source_repo: str,
    release_name: str,
    published_at: str,
    source_url: str,
    body: str,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for raw in body.splitlines():
        statement = _clean_statement(raw)
        if len(statement) < 20 or len(statement) > 500:
            continue
        lower = statement.lower()
        score, matched = _relevance(statement)
        if score < MIN_RELEVANCE_SCORE or not matched:
            continue
        if not any(hint in lower for hint in ACTION_HINTS) and score < 10:
            continue
        name = _capability_name(statement)
        fp = _fingerprint(name)
        if fp in seen:
            continue
        seen.add(fp)
        candidates.append(
            Candidate(
                source_repo=source_repo,
                release_name=release_name,
                published_at=published_at,
                source_url=source_url,
                statement=statement,
                capability_name=name,
                fingerprint=fp,
                score=score,
                matched_needs=matched,
            )
        )
    return candidates


def recent_release_candidates(token: str | None, now: datetime | None = None) -> list[Candidate]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=RECENT_DAYS)
    result: list[Candidate] = []
    for repo in SOURCES:
        url = f"https://api.github.com/repos/{repo}/releases?" + urllib.parse.urlencode(
            {"per_page": MAX_RELEASES_PER_SOURCE}
        )
        try:
            releases = _request_json(url, token)
        except (OSError, ValueError, urllib.error.URLError):
            continue
        if not isinstance(releases, list):
            continue
        for release in releases:
            if not isinstance(release, dict) or release.get("draft"):
                continue
            published = str(release.get("published_at") or release.get("created_at") or "")
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
            if published_dt < cutoff:
                continue
            result.extend(
                extract_candidates(
                    repo,
                    str(release.get("name") or release.get("tag_name") or "release"),
                    published,
                    str(release.get("html_url") or ""),
                    str(release.get("body") or ""),
                )
            )
    result.sort(key=lambda item: (item.published_at, item.score), reverse=True)
    return result


def _registered_capability_texts(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    texts: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else ""
        if name != "register_capability" or len(node.args) < 2:
            continue
        parts: list[str] = []
        for arg in node.args[:3]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                parts.append(arg.value)
        if parts:
            texts.append(" ".join(parts))
    return texts


def _all_issue_texts(repo: str, token: str) -> list[str]:
    texts: list[str] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{repo}/issues?" + urllib.parse.urlencode(
            {
                "state": "all",
                "sort": "created",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        rows = _request_json(url, token)
        if not isinstance(rows, list):
            break
        for row in rows:
            if not isinstance(row, dict) or "pull_request" in row:
                continue
            texts.append(f"{row.get('title') or ''}\n{row.get('body') or ''}")
        if len(rows) < 100:
            break
    return texts


def _already_known(candidate: Candidate, existing_texts: Iterable[str]) -> bool:
    marker = f"genesis-capability-discovery:{candidate.fingerprint}"
    for text in existing_texts:
        lower = text.lower()
        if marker in lower:
            return True
        if candidate.source_url and candidate.source_url.lower() in lower:
            return True
        if _similarity(candidate.capability_name, text) >= 0.58:
            return True
    return False


def choose_candidate(
    candidates: Iterable[Candidate],
    repository_capabilities: Iterable[str],
    issue_texts: Iterable[str],
) -> Candidate | None:
    known = list(repository_capabilities) + list(issue_texts)
    for candidate in candidates:
        if _already_known(candidate, known):
            continue
        return candidate
    return None


def _issue_body(candidate: Candidate) -> str:
    task_id = f"task-{candidate.fingerprint}"
    needs = ", ".join(candidate.matched_needs[:6])
    evidence = (
        f"{candidate.source_repo} release {candidate.release_name!r}, published "
        f"{candidate.published_at}: {candidate.statement}. Source: {candidate.source_url}"
    )
    return f"""<!-- genesis-capability-discovery:{candidate.fingerprint} -->
<!-- genesis-task-id:{task_id} -->
This GitHub Issue is the authoritative task record for one newly published AI capability selected by the independent Genesis Capability Discovery task.

Genesis-Problem-Fingerprint: recent-ai-capability:{candidate.fingerprint}
- **Genesis task ID:** `{task_id}`
- **Task type:** `new_capability`
- **Source:** `genesis.evolution_learning`
- **Priority:** 70
- **Target:** `genesis/learned_capabilities.py`

### Objective
Use the learned idea: {candidate.capability_name}. Acceptance: add one bounded executable Genesis capability grounded in the cited publication evidence; do not copy provider identity, secrets, unsafe network behavior, or benchmark answers.
External learning evidence: {evidence}
Incubator evidence: This is a verified transferable lesson selected because it is recently published, not already represented in Genesis, and relevant to current Genesis needs ({needs}).
Target exactly genesis/learned_capabilities.py.

### Acceptance
- Implement only the smallest bounded executable capability justified by the evidence.
- Preserve tests, Security, validation, provenance, protected-file boundaries, signing boundaries, secret boundaries, and owner control.
- Do not self-award benchmark or capability score.
- Existing Issue Solver and bounded repair process remain the only implementation lane.

### Discovery rule
The Capability Discovery task only creates this issue. It must not implement, repair, promote, or close the issue.
"""


def create_issue(repo: str, token: str, candidate: Candidate) -> str:
    payload = {
        "title": f"[Genesis Task] new capability — {candidate.capability_name}",
        "body": _issue_body(candidate),
        "labels": ["genesis-task", "genesis-capability-discovery"],
    }
    response = _post_json(f"https://api.github.com/repos/{repo}/issues", payload, token)
    if not isinstance(response, dict):
        raise RuntimeError("GitHub returned an invalid issue response")
    return str(response.get("html_url") or response.get("url") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create at most one issue for one recent AI capability.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not repo:
        print("No GITHUB_REPOSITORY; nothing created.")
        return 0
    if not token and not args.dry_run:
        print("No GitHub token; nothing created.")
        return 0

    candidates = recent_release_candidates(token or None)
    registry_texts = _registered_capability_texts(Path("genesis/learned_capabilities.py"))
    issue_texts = _all_issue_texts(repo, token) if token else []
    candidate = choose_candidate(candidates, registry_texts, issue_texts)

    if candidate is None:
        print("No qualifying recent, required, non-duplicate AI capability found.")
        return 0

    print(
        json.dumps(
            {
                "capability": candidate.capability_name,
                "source_repo": candidate.source_repo,
                "release": candidate.release_name,
                "published_at": candidate.published_at,
                "source_url": candidate.source_url,
                "fingerprint": candidate.fingerprint,
                "score": candidate.score,
                "matched_needs": candidate.matched_needs,
            },
            indent=2,
        )
    )
    if args.dry_run:
        return 0

    issue_url = create_issue(repo, token, candidate)
    print(f"Created capability issue: {issue_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

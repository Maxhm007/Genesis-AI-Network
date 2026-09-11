from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
LEARNED = ROOT / "genesis" / "learned_capabilities.py"


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    title: str
    description: str
    evidence_paths: tuple[str, ...]
    registry_terms: tuple[str, ...]
    reference: str
    priority: int = 72


BASELINE: tuple[CapabilityGap, ...] = (
    CapabilityGap(
        "computer_use",
        "Computer-use interaction",
        "Observe and act on graphical interfaces through a bounded, verifiable computer-use loop.",
        ("genesis/computer_use.py", "genesis/gui_automation.py", "genesis/desktop_control.py"),
        ("computer_use", "gui_automation", "desktop_control"),
        "https://github.com/microsoft/autogen",
    ),
    CapabilityGap(
        "structured_output_schema",
        "Schema-constrained structured output",
        "Generate and validate machine-readable model output against an explicit schema.",
        ("genesis/structured_output.py", "genesis/schema_output.py"),
        ("structured_output", "json_schema", "schema_constrained_output"),
        "https://platform.openai.com/docs/guides/structured-outputs",
    ),
    CapabilityGap(
        "tool_call_planning",
        "Multi-step tool-call planning",
        "Plan, execute, verify, and revise bounded sequences of tool calls.",
        ("genesis/tool_planner.py", "genesis/tool_execution.py"),
        ("tool_call_planning", "tool_planner", "multi_step_tool_use"),
        "https://github.com/langchain-ai/langgraph",
    ),
    CapabilityGap(
        "retrieval_grounding",
        "Retrieval-grounded generation",
        "Ground model output in retrieved evidence with provenance and reject unsupported claims.",
        ("genesis/retrieval.py", "genesis/rag.py", "genesis/retrieval_grounding.py"),
        ("retrieval_grounding", "grounded_retrieval", "rag"),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "context_compaction",
        "Long-context compaction",
        "Compact older context while preserving task-critical state for long-running agents.",
        ("genesis/context_compaction.py", "genesis/context_memory.py"),
        ("context_compaction", "context_compression", "long_context_compaction"),
        "https://github.com/vllm-project/vllm",
    ),
    CapabilityGap(
        "multimodal_vision",
        "Image understanding",
        "Accept image inputs and expose grounded visual observations to Genesis reasoning and tools.",
        ("genesis/vision.py", "genesis/multimodal.py", "genesis/image_understanding.py"),
        ("multimodal_vision", "image_understanding", "vision_input"),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "audio_understanding",
        "Audio and speech understanding",
        "Process bounded audio or speech inputs into structured evidence usable by Genesis.",
        ("genesis/audio.py", "genesis/speech.py", "genesis/audio_understanding.py"),
        ("audio_understanding", "speech_recognition", "audio_input"),
        "https://github.com/huggingface/transformers",
    ),
    CapabilityGap(
        "persistent_memory",
        "Persistent agent memory",
        "Store and retrieve bounded long-lived task knowledge across runs with provenance and lifecycle controls.",
        ("genesis/persistent_memory.py", "genesis/memory_store.py"),
        ("persistent_memory", "long_term_memory", "memory_store"),
        "https://github.com/microsoft/autogen",
    ),
)


def registered_capability_names(path: Path = LEARNED) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ()
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "register_capability" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.append(first.value.strip().lower())
    return tuple(names)


def capability_present(gap: CapabilityGap, root: Path = ROOT, registry_names: Iterable[str] | None = None) -> bool:
    for relative in gap.evidence_paths:
        if (root / relative).is_file():
            return True
    names = tuple(name.lower() for name in (registry_names if registry_names is not None else registered_capability_names()))
    return any(any(term in name for term in gap.registry_terms) for name in names)


def fingerprint(capability_id: str) -> str:
    return hashlib.sha256(capability_id.encode("utf-8")).hexdigest()[:16]


def choose_missing(root: Path, registry_names: Iterable[str], issue_texts: Iterable[str]) -> CapabilityGap | None:
    issues = "\n".join(issue_texts).lower()
    names = tuple(registry_names)
    for gap in BASELINE:
        marker = f"genesis-missing-capability:{fingerprint(gap.capability_id)}"
        if marker in issues:
            continue
        if capability_present(gap, root, names):
            continue
        return gap
    return None


def _request_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-AI-Network/missing-capability-discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, token: str, payload: dict) -> object:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-AI-Network/missing-capability-discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def all_issue_texts(repo: str, token: str) -> list[str]:
    texts: list[str] = []
    for page in range(1, 11):
        url = f"https://api.github.com/repos/{repo}/issues?" + urllib.parse.urlencode(
            {"state": "all", "per_page": 100, "page": page}
        )
        rows = _request_json(url, token)
        if not isinstance(rows, list):
            break
        for row in rows:
            if isinstance(row, dict) and "pull_request" not in row:
                texts.append(f"{row.get('title') or ''}\n{row.get('body') or ''}")
        if len(rows) < 100:
            break
    return texts


def issue_body(gap: CapabilityGap) -> str:
    fp = fingerprint(gap.capability_id)
    task_id = f"task-missing-{fp}"
    return f"""<!-- genesis-missing-capability:{fp} -->
<!-- genesis-task-id:{task_id} -->
This GitHub Issue is the authoritative task record for one capability that the Qwen-based Genesis baseline is missing.

Genesis-Problem-Fingerprint: missing-qwen-capability:{fp}
- **Genesis task ID:** `{task_id}`
- **Task type:** `new_capability`
- **Capability subtype:** `missing_capability`
- **Source:** `genesis.qwen_gap_audit`
- **Priority:** {gap.priority}
- **Target:** `genesis/learned_capabilities.py`

### Missing capability
**{gap.title}**

{gap.description}

### Why this issue exists
The independent Missing Capability Discovery task found neither an accepted implementation module nor a registered learned capability for `{gap.capability_id}`.
Reference capability evidence: {gap.reference}

### Objective
Add the smallest bounded executable capability that closes this gap for the Qwen-based Genesis system. Qwen remains the base model; this task upgrades what Genesis can do around that base model.

### Acceptance
- Add an executable capability or integration that demonstrably closes the named gap.
- Add focused tests proving the capability works and fails safely.
- Preserve Security, validation, provenance, protected-file boundaries, signing boundaries, secret boundaries, and owner control.
- Do not self-award benchmark or capability score.
- Existing Issue Solver and bounded repair process remain the only implementation lane.

### Discovery rule
This Missing Capability Discovery task only opens the issue. It does not implement, promote, repair, or close it.
"""


def create_issue(repo: str, token: str, gap: CapabilityGap) -> str:
    payload = {
        "title": f"[Genesis Task] new capability — missing baseline: {gap.title}",
        "body": issue_body(gap),
        "labels": ["genesis-task", "genesis-capability-discovery", "genesis-missing-capability"],
    }
    result = _post_json(f"https://api.github.com/repos/{repo}/issues", token, payload)
    if not isinstance(result, dict):
        raise RuntimeError("invalid GitHub issue response")
    return str(result.get("html_url") or result.get("url") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open at most one issue for one missing Qwen/Genesis capability.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not repo:
        print(json.dumps({"status": "no_repository"}, sort_keys=True))
        return 0
    if not token and not args.dry_run:
        print(json.dumps({"status": "no_token"}, sort_keys=True))
        return 0

    issues = all_issue_texts(repo, token) if token else []
    gap = choose_missing(ROOT, registered_capability_names(), issues)
    if gap is None:
        print(json.dumps({"status": "no_missing_capability"}, sort_keys=True))
        return 0

    payload = {
        "status": "missing_capability_found",
        "capability_id": gap.capability_id,
        "title": gap.title,
        "fingerprint": fingerprint(gap.capability_id),
    }
    if args.dry_run:
        payload["issue_body"] = issue_body(gap)
        print(json.dumps(payload, sort_keys=True))
        return 0

    payload["issue_url"] = create_issue(repo, token, gap)
    payload["status"] = "missing_capability_issue_created"
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

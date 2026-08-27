from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from .coding import CodingModule
from .deterministic_capability_builder import DeterministicLearnedCapabilityProvider


class GitHubIssueLearnedCapabilityProvider(DeterministicLearnedCapabilityProvider):
    """Adapt trusted Genesis-generated GitHub capability tasks to the deterministic builder.

    GitHub issue text remains untrusted evidence. This adapter only activates for
    the exact machine-authored task envelope emitted by Genesis evolution learning,
    and template selection still depends on explicit deterministic patterns rather
    than treating prose as executable instructions.
    """

    MACHINE_AUTHOR = "github-actions[bot]"
    TASK_MARKER = "<!-- genesis-task-id:task-"
    TASK_TYPE_LINE = "- **Task type:** `new_capability`"
    SOURCE_LINE = "- **Source:** `genesis.evolution_learning`"
    TARGET_LINE = "- **Target:** `genesis/learned_capabilities.py`"

    @classmethod
    def _render_template(cls, token: str, combined: str) -> tuple[str, str, str] | None:
        if (
            ("build once" in combined or "build ui once" in combined)
            and "artifact" in combined
            and ("reuse" in combined or "prebuilt" in combined)
        ):
            function_name = f"_learned_{token}"
            capability_name = f"reusable_build_artifact_{token}"
            handler = f'''def {function_name}(
    artifact_name: str,
    available_artifacts,
    build_allowed: bool = True,
) -> tuple[str, bool]:
    """Reuse an already-built artifact and request a build only when it is missing."""
    artifact = str(artifact_name).strip()
    if not artifact:
        raise ValueError("artifact name is required")
    available: list[str] = []
    for item in available_artifacts:
        value = str(item).strip()
        if value and value not in available:
            available.append(value)
        if len(available) > 256:
            raise ValueError("available artifact set exceeds bounded size")
    if artifact in available:
        return artifact, False
    return artifact, bool(build_allowed)
'''
            description = "Reuse an already-built/prebuilt artifact when available and request a build only when it is missing."
            return capability_name, description, handler
        return super()._render_template(token, combined)

    @classmethod
    def for_issue(
        cls,
        root: Path,
        issue: dict,
        coding: CodingModule,
    ) -> GitHubIssueLearnedCapabilityProvider | None:
        author = str(dict(issue.get("user") or {}).get("login") or "")
        title = str(issue.get("title") or "").strip()
        body = str(issue.get("body") or "")
        if author != cls.MACHINE_AUTHOR:
            return None
        if not title.startswith("[Genesis Task] new capability"):
            return None
        if cls.TASK_MARKER not in body:
            return None
        if cls.TASK_TYPE_LINE not in body or cls.SOURCE_LINE not in body or cls.TARGET_LINE not in body:
            return None
        if "verified transferable lesson" not in body.lower() or "External learning evidence:" not in body:
            return None

        objective_match = re.search(r"(?s)### Objective\s*(.+?)(?:\n\n### Acceptance|\Z)", body)
        if objective_match is None:
            return None
        objective = objective_match.group(1).strip()
        learned_match = re.search(r"Use the learned idea:\s*(.+?)(?:\s+Acceptance:|\s+External learning evidence:)", objective, re.S)
        evidence_match = re.search(r"External learning evidence:\s*(.+?)(?:\s+\* Incubator evidence:|\s+Target exactly|\Z)", objective, re.S)
        if learned_match is None or evidence_match is None:
            return None

        lesson = cls._bounded_text(learned_match.group(1), cls.MAX_LESSON_BYTES)
        evidence = cls._bounded_text(evidence_match.group(1), cls.MAX_EVIDENCE_BYTES)
        if not lesson or not evidence:
            return None

        token_match = re.search(r"\blearned_([0-9a-fA-F]{12,64})\b", title)
        fingerprint = token_match.group(1).lower() if token_match else ""
        task = SimpleNamespace(
            payload={
                "source": "genesis.evolution_learning",
                "target_path": cls.TARGET,
                "learning": {"fingerprint": fingerprint},
                "discovery": {
                    "finding": {
                        "decision": "upgrade",
                        "grounded": True,
                        "new_capability": True,
                        "lesson": lesson,
                        "lesson_evidence": evidence,
                        "lesson_topics": ["artifact_reuse", "build_efficiency"],
                        "summary": lesson,
                    }
                },
            }
        )
        return super().for_task(Path(root).resolve(), task, coding)

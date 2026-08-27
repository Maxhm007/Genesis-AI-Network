from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from .coding import CodingModule
from .deterministic_capability_builder import DeterministicLearnedCapabilityProvider


class GitHubIssueLearnedCapabilityProvider(DeterministicLearnedCapabilityProvider):
    """Adapt trusted Genesis-generated GitHub capability tasks to deterministic builders.

    GitHub issue text remains untrusted evidence. This adapter only activates for
    the exact machine-authored task envelope emitted by Genesis evolution learning.
    Known lessons use explicit deterministic templates. Other structured lessons
    use a syntax-safe evidence-grounding capability instead of free-form code
    generation; unrelated or user-authored issues still fall back to the bounded
    coding-provider route.
    """

    MACHINE_AUTHOR = "github-actions[bot]"
    TASK_MARKER = "<!-- genesis-task-id:task-"
    TASK_TYPE_LINE = "- **Task type:** `new_capability`"
    SOURCE_LINE = "- **Source:** `genesis.evolution_learning`"
    TARGET_LINE = "- **Target:** `genesis/learned_capabilities.py`"
    MAX_GENERIC_TERMS = 16
    GENERIC_STOPWORDS = {
        "acceptance",
        "capability",
        "candidate",
        "external",
        "genesis",
        "implementing",
        "learned",
        "learning",
        "release",
        "research",
        "source",
        "transferable",
        "verified",
    }

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
    def _generic_terms(cls, lesson: str, evidence: str) -> tuple[str, ...]:
        terms: list[str] = []
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{3,}", f"{lesson}\n{evidence}"):
            value = token.lower().strip("._+-")
            if len(value) < 4 or value in cls.GENERIC_STOPWORDS or value in terms:
                continue
            terms.append(value)
            if len(terms) >= cls.MAX_GENERIC_TERMS:
                break
        return tuple(terms)

    @classmethod
    def _generic_issue_provider(
        cls,
        root: Path,
        coding: CodingModule,
        *,
        fingerprint: str,
        lesson: str,
        evidence: str,
    ) -> GitHubIssueLearnedCapabilityProvider | None:
        token = cls._token(fingerprint, lesson, evidence)
        capability_suffix = fingerprint.lower() if fingerprint else token
        capability_name = f"learned_{capability_suffix}"
        function_name = f"_learned_{token}"
        terms = cls._generic_terms(lesson, evidence)
        if not terms:
            terms = (token,)

        target = (Path(root).resolve() / cls.TARGET).resolve()
        if not target.is_file():
            return None
        current = target.read_text(encoding="utf-8")
        if current.count(cls.MARKER) != 1:
            raise RuntimeError("learned capability insertion marker is missing or ambiguous")
        if f'"{capability_name}"' in current or f"'{capability_name}'" in current:
            return None

        handler = f'''def {function_name}(items, limit: int = 32) -> tuple[str, ...]:
    """Return bounded caller values explicitly grounded in verified lesson terms."""
    limit_i = int(limit)
    if limit_i < 1 or limit_i > 128:
        raise ValueError("lesson-grounding limit is out of bounds")
    terms = {terms!r}
    source = (items,) if isinstance(items, (str, bytes)) else items
    grounded: list[str] = []
    scanned = 0
    for item in source:
        scanned += 1
        if scanned > 256:
            break
        if isinstance(item, bytes):
            value = item.decode("utf-8", errors="replace").strip()
        else:
            value = str(item).strip()
        if not value:
            continue
        bounded = value[:512]
        lowered = bounded.lower()
        if any(term in lowered for term in terms):
            grounded.append(bounded)
        if len(grounded) >= limit_i:
            break
    return tuple(grounded)
'''
        description = (
            "Ground bounded candidate context against terms derived only from the verified lesson/evidence before downstream use. "
            "Verified lesson: "
            + lesson
        )
        registration = (
            handler
            + "\n"
            + "register_capability(\n"
            + f"    {capability_name!r},\n"
            + f"    {description!r},\n"
            + f"    {evidence!r},\n"
            + f"    {function_name},\n"
            + ")\n"
        )
        updated = current.replace(cls.MARKER, registration + "\n\n" + cls.MARKER, 1)
        proposal = {
            "title": f"Add learned capability {capability_name}",
            "rationale": (
                "Deterministic syntax-safe capability synthesis from the explicit machine-authored GitHub task envelope and verified evidence."
            ),
            "files": {cls.TARGET: updated},
        }
        coding.validate_proposal(proposal, cls.name)
        return cls(proposal)

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
        evidence_match = re.search(
            r"External learning evidence:\s*(.+?)(?:\s+\*?\s*Incubator evidence:|\s+Target exactly|\Z)",
            objective,
            re.S,
        )
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
        specialized = super().for_task(Path(root).resolve(), task, coding)
        if specialized is not None:
            return specialized
        return cls._generic_issue_provider(
            Path(root).resolve(),
            coding,
            fingerprint=fingerprint,
            lesson=lesson,
            evidence=evidence,
        )

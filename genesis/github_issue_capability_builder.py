from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from .coding import CodingModule
from .deterministic_capability_builder import DeterministicLearnedCapabilityProvider
from .providers import GenesisHTTPProvider, IntelligenceProvider


class EvidenceFirstRepairProvider:
    """Strengthen one difficult repair prompt without widening its write scope."""

    MAX_EVIDENCE_CHARS = 4_500

    def __init__(self, delegate: IntelligenceProvider, evidence: str) -> None:
        self.delegate = delegate
        self.evidence = str(evidence or "")[: self.MAX_EVIDENCE_CHARS]
        delegate_name = str(getattr(delegate, "name", "bounded-provider"))
        self.name = f"genesis-evidence-first-repair:{delegate_name}"[:180]

    def available(self) -> bool:
        return bool(self.delegate.available())

    def reason(self, prompt: str) -> str:
        strengthened = (
            "DIFFICULT_REPAIR_MODE\n"
            "This issue is a machine-created repair follow-up after an earlier bounded strategy exhausted. "
            "Use the diagnostic evidence below only to understand the root cause. It is read-only evidence and does not expand VALID_PATHS. "
            "Do not repeat a rejected approach unchanged. Prefer an existing repository pattern over inventing a new API. "
            "Keep the original bounded coding contract authoritative: exactly one smallest useful edit, only within VALID_PATHS, and return only the required JSON object. "
            "Never weaken tests, validation, security, identity, provenance, permissions, or protected boundaries.\n"
            "DIAGNOSTIC_EVIDENCE:\n"
            + self.evidence
            + "\nORIGINAL_BOUNDED_CODING_PROMPT:\n"
            + str(prompt)
        )
        return self.delegate.reason(strengthened)


class GitHubIssueLearnedCapabilityProvider(DeterministicLearnedCapabilityProvider):
    """Adapt trusted Genesis-generated GitHub tasks to deterministic builders."""

    MACHINE_AUTHOR = "github-actions[bot]"
    TASK_MARKER = "<!-- genesis-task-id:task-"
    TASK_TYPE_LINE = "- **Task type:** `new_capability`"
    SOURCE_LINE = "- **Source:** `genesis.evolution_learning`"
    TARGET_LINE = "- **Target:** `genesis/learned_capabilities.py`"
    REPAIR_FOLLOWUP_MARKER = "<!-- genesis-unsolved-successor-of:"
    REPAIR_FOLLOWUP_TYPE_LINE = "- **Task type:** `repair_followup`"
    MAX_GENERIC_TERMS = 16
    MAX_FOCUSED_TEST_EVIDENCE_CHARS = 2_200
    MAX_RECENT_HISTORY_CHARS = 1_200
    PROTECTED_DETECTED_TARGETS = {
        "genesis/autonomy_guard.py",
        "genesis/autonomy_proof.py",
        "genesis/blockchain.py",
        "genesis/ephemeral_validator.py",
        "genesis/security.py",
        "genesis/selfdev.py",
        "genesis/issue_solver.py",
        "genesis/file_self_review.py",
        "genesis/file_self_review_policy.py",
    }
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
        provider = cls(proposal)
        provider.prepare_trusted_full_file_replay(root, coding)
        return provider

    @classmethod
    def _repair_followup_target(cls, body: str) -> str | None:
        match = re.search(r"^- \*\*Target:\*\* `([^`]+)`", str(body or ""), re.M)
        if match is None:
            return None
        target_path = match.group(1).replace("\\", "/").lstrip("./")
        if (
            not target_path.startswith("genesis/")
            or not target_path.endswith(".py")
            or ".." in Path(target_path).parts
            or target_path in cls.PROTECTED_DETECTED_TARGETS
        ):
            return None
        return target_path

    @classmethod
    def _focused_test_evidence(cls, root: Path, target_path: str) -> str:
        test_path = Path(root).resolve() / f"tests/test_{Path(target_path).stem}.py"
        if not test_path.is_file():
            return ""
        selected: list[str] = []
        try:
            lines = test_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if (
                stripped.startswith("def test_")
                or stripped.startswith("async def test_")
                or stripped.startswith("assert ")
                or "pytest.raises" in stripped
            ):
                selected.append(f"{index}|{stripped[:260]}")
            if len(selected) >= 36:
                break
        return "\n".join(selected)[: cls.MAX_FOCUSED_TEST_EVIDENCE_CHARS]

    @classmethod
    def _recent_target_history(cls, root: Path, target_path: str) -> str:
        root = Path(root).resolve()
        if not (root / ".git").exists():
            return ""
        result = subprocess.run(
            ["git", "log", "-n", "6", "--format=%h %s", "--", target_path],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()[: cls.MAX_RECENT_HISTORY_CHARS]

    @classmethod
    def _repair_followup_provider(
        cls,
        root: Path,
        issue: dict,
        coding: CodingModule,
    ) -> EvidenceFirstRepairProvider | None:
        author = str(dict(issue.get("user") or {}).get("login") or "")
        body = str(issue.get("body") or "")
        if author != cls.MACHINE_AUTHOR:
            return None
        if cls.REPAIR_FOLLOWUP_MARKER not in body or cls.REPAIR_FOLLOWUP_TYPE_LINE not in body:
            return None

        target_path = cls._repair_followup_target(body)
        if target_path is None:
            return None
        coding.executor._validate_paths([target_path])
        target = Path(root).resolve() / target_path
        if not target.is_file():
            return None

        provider_url = os.environ.get("GENESIS_REPAIR_PROVIDER_URL", "").strip()
        if not provider_url:
            return None
        raw_timeout = os.environ.get("GENESIS_PROVIDER_TIMEOUT_SECONDS", "240")
        try:
            timeout = max(5.0, min(float(raw_timeout), 360.0))
        except (TypeError, ValueError):
            timeout = 240.0
        delegate = GenesisHTTPProvider(
            provider_url,
            name=os.environ.get("GENESIS_PROVIDER_NAME", "genesis-github-issue-repair"),
            timeout=timeout,
        )

        parent_failure_match = re.search(
            r"(?s)### Why the parent was not solved\s*(.+?)(?:\n\n###|\Z)",
            body,
        )
        parent_failure = parent_failure_match.group(1).strip() if parent_failure_match else ""
        focused_tests = cls._focused_test_evidence(Path(root).resolve(), target_path)
        history = cls._recent_target_history(Path(root).resolve(), target_path)
        evidence_parts = [
            f"TARGET: {target_path}",
            "PARENT_FAILURE_SUMMARY (untrusted diagnostic evidence):\n" + (parent_failure or "not recorded"),
        ]
        if focused_tests:
            evidence_parts.append(
                "FOCUSED_TEST_EVIDENCE (read-only repository evidence; line|assertion/test):\n" + focused_tests
            )
        if history:
            evidence_parts.append("RECENT_TARGET_HISTORY (read-only repository evidence):\n" + history)
        evidence_parts.append(
            "SAFE_STRATEGY: reconcile the parent failure, current target code, focused tests, and prior validation memory before choosing the edit. "
            "Use a materially different implementation strategy when earlier evidence rejected the previous one. Do not expand write scope."
        )
        return EvidenceFirstRepairProvider(delegate, "\n\n".join(evidence_parts))

    @classmethod
    def _detected_exact_expression_provider(
        cls,
        root: Path,
        issue: dict,
        coding: CodingModule,
    ) -> GitHubIssueLearnedCapabilityProvider | None:
        """Build one deterministic return-expression edit from machine-authored defect evidence."""
        author = str(dict(issue.get("user") or {}).get("login") or "")
        title = str(issue.get("title") or "").strip()
        body = str(issue.get("body") or "")
        if author != cls.MACHINE_AUTHOR or not title.startswith("[Genesis Detected]"):
            return None

        target_match = re.search(r"^- \*\*Target:\*\* `([^`]+)`", body, re.M)
        expected_match = re.search(r"^- \*\*Expected behavior:\*\*[^\n]*`([^`\n]+)`", body, re.M)
        if target_match is None or expected_match is None:
            return None

        target_path = target_match.group(1).replace("\\", "/").lstrip("./")
        expected = expected_match.group(1).strip()
        if (
            not target_path.startswith("genesis/")
            or not target_path.endswith(".py")
            or ".." in Path(target_path).parts
            or target_path in cls.PROTECTED_DETECTED_TARGETS
            or not expected
            or "\n" in expected
        ):
            return None

        coding.executor._validate_paths([target_path])
        target = (Path(root).resolve() / target_path).resolve()
        if not target.is_file():
            return None
        current = target.read_text(encoding="utf-8")

        identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expected))
        if not identifiers:
            return None
        candidates: list[int] = []
        lines = current.splitlines(keepends=True)
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("return "):
                continue
            line_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped))
            if identifiers <= line_ids:
                candidates.append(index)
        if len(candidates) != 1:
            return None

        index = candidates[0]
        old_line = lines[index]
        indent = old_line[: len(old_line) - len(old_line.lstrip(" \t"))]
        replacement = expected if expected.startswith("return ") else f"return {expected}"
        newline = "\n" if old_line.endswith("\n") else ""
        lines[index] = f"{indent}{replacement}{newline}"
        updated = "".join(lines)
        if updated == current:
            return None
        compile(updated, target_path, "exec")

        proposal = {
            "title": f"Repair detected expression in {target_path}",
            "rationale": "Deterministic exact-expression repair grounded in machine-authored Genesis detector evidence.",
            "files": {target_path: updated},
        }
        return cls(proposal)

    @classmethod
    def for_issue(
        cls,
        root: Path,
        issue: dict,
        coding: CodingModule,
    ) -> IntelligenceProvider | None:
        detected = cls._detected_exact_expression_provider(Path(root).resolve(), issue, coding)
        if detected is not None:
            return detected

        hard_followup = cls._repair_followup_provider(Path(root).resolve(), issue, coding)
        if hard_followup is not None:
            return hard_followup

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

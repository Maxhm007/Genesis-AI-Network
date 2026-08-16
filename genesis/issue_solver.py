from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .selfdev import SelfDevelopmentExecutor, SelfDevResult

PROTECTED_PATHS = {"GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"}
ALLOWED_PREFIXES = ("genesis/", "tests/", "docs/", "config/")
MAX_PATCH_FILES = 6
MAX_PATCH_BYTES = 80_000


@dataclass(frozen=True)
class Diagnosis:
    category: str
    summary: str
    failure_text: str


@dataclass(frozen=True)
class RepairAttempt:
    diagnosis: Diagnosis
    proposal: dict | None
    result: SelfDevResult | None
    status: str


class IssueSolver:
    """Bounded self-healing controller for Genesis software issues.

    The solver diagnoses its own test failures, tries deterministic repair recipes,
    and can optionally ask a configured Genesis Provider Protocol endpoint for a
    structured patch. All patches remain restricted to non-protected paths and are
    executed through SelfDevelopmentExecutor, so they must pass the full test suite
    before becoming a candidate commit. The solver never merges to main itself.
    """

    def __init__(self, root: Path, provider_url: str | None = None) -> None:
        self.root = root.resolve()
        self.provider_url = (provider_url or os.environ.get("GENESIS_REPAIR_PROVIDER_URL", "")).rstrip("/")

    def run_tests(self) -> tuple[bool, str]:
        proc = subprocess.run(
            [os.environ.get("PYTHON", "python"), "-m", "pytest", "-q"],
            cwd=self.root,
            text=True,
            capture_output=True,
        )
        text = (proc.stdout + "\n" + proc.stderr)[-24_000:]
        return proc.returncode == 0, text

    def diagnose(self, failure_text: str) -> Diagnosis:
        text = failure_text.lower()
        if "waiting_for_provider" in text and "providerregistry" in text:
            return Diagnosis(
                "provider_mode_expectation",
                "Tests appear to assume an empty provider registry while the native bootstrap provider is enabled by default.",
                failure_text,
            )
        if "modulenotfounderror" in text or "importerror" in text:
            return Diagnosis("import_failure", "A module/import dependency failed.", failure_text)
        if "syntaxerror" in text:
            return Diagnosis("syntax_failure", "Python syntax is invalid in the candidate tree.", failure_text)
        if "constitution" in text and ("mismatch" in text or "verification failed" in text):
            return Diagnosis("constitution_integrity", "Genesis Constitution verification failed; automated repair is forbidden.", failure_text)
        return Diagnosis("unknown_test_failure", "The test suite failed without a recognized deterministic repair signature.", failure_text)

    def _deterministic_proposal(self, diagnosis: Diagnosis) -> dict | None:
        if diagnosis.category != "provider_mode_expectation":
            return None

        replacements: dict[str, str] = {}
        for relative in (
            "tests/test_provider_modes.py",
            "tests/test_team_and_peers.py",
            "tests/test_dynamic_team.py",
        ):
            path = self.root / relative
            if not path.exists():
                continue
            original = path.read_text(encoding="utf-8")
            updated = original
            # Only alter tests that explicitly assert an empty-provider behavior.
            if "waiting_for_provider" in original or '"maintenance"' in original or "'maintenance'" in original:
                updated = re.sub(r"ProviderRegistry\(\)", "ProviderRegistry(include_bootstrap=False)", updated)
            # Provider routing tests should not accidentally include bootstrap alongside a fake provider.
            if "fake-provider" in original:
                updated = re.sub(r"ProviderRegistry\(\)", "ProviderRegistry(include_bootstrap=False)", updated)
            if updated != original:
                replacements[relative] = updated

        if not replacements:
            return None
        return {
            "title": "Repair stale empty-provider test assumptions",
            "rationale": diagnosis.summary,
            "files": replacements,
        }

    def _provider_proposal(self, diagnosis: Diagnosis) -> dict | None:
        if not self.provider_url or diagnosis.category == "constitution_integrity":
            return None
        prompt = {
            "task": "Repair the Genesis AI repository test failure with the smallest safe patch.",
            "constraints": {
                "protected_paths": sorted(PROTECTED_PATHS),
                "allowed_prefixes": list(ALLOWED_PREFIXES),
                "max_files": MAX_PATCH_FILES,
                "max_total_bytes": MAX_PATCH_BYTES,
                "requirements": [
                    "Return JSON only with title, rationale, and files mapping relative paths to COMPLETE replacement file contents.",
                    "Do not change the Genesis Constitution or Genesis Block.",
                    "Do not disable, skip, xfail, or weaken tests merely to obtain a pass.",
                    "Prefer fixing production code over changing tests unless the test is demonstrably stale relative to an intentional documented behavior.",
                ],
            },
            "diagnosis": {"category": diagnosis.category, "summary": diagnosis.summary},
            "failure_text": diagnosis.failure_text[-16_000:],
        }
        req = urllib.request.Request(
            self.provider_url + "/reason",
            data=json.dumps({"prompt": json.dumps(prompt, sort_keys=True)}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Genesis-AI-Network/0.1"},
        )
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get("response", "")
        proposal = json.loads(raw) if isinstance(raw, str) else raw
        return self.validate_proposal(proposal)

    def validate_proposal(self, proposal: dict) -> dict:
        if not isinstance(proposal, dict) or not isinstance(proposal.get("files"), dict):
            raise ValueError("repair proposal must contain a files mapping")
        files = proposal["files"]
        if not files or len(files) > MAX_PATCH_FILES:
            raise ValueError("repair proposal file count out of bounds")
        total = 0
        for relative, content in files.items():
            normalized = str(relative).replace("\\", "/").lstrip("./")
            if normalized in PROTECTED_PATHS or not normalized.startswith(ALLOWED_PREFIXES):
                raise ValueError(f"repair path not allowed: {normalized}")
            if not isinstance(content, str):
                raise ValueError("repair content must be text")
            total += len(content.encode("utf-8"))
            if normalized.endswith(".py"):
                ast.parse(content, filename=normalized)
        if total > MAX_PATCH_BYTES:
            raise ValueError("repair proposal too large")
        return {"title": str(proposal.get("title", "Genesis autonomous repair")), "rationale": str(proposal.get("rationale", "")), "files": files}

    def solve_once(self) -> RepairAttempt:
        passed, failure_text = self.run_tests()
        if passed:
            diagnosis = Diagnosis("healthy", "All tests pass; no repair is needed.", failure_text)
            return RepairAttempt(diagnosis, None, None, "healthy")

        diagnosis = self.diagnose(failure_text)
        if diagnosis.category == "constitution_integrity":
            return RepairAttempt(diagnosis, None, None, "blocked_protected_identity")

        proposal = self._deterministic_proposal(diagnosis)
        if proposal is None:
            try:
                proposal = self._provider_proposal(diagnosis)
            except Exception:
                proposal = None
        if proposal is None:
            return RepairAttempt(diagnosis, None, None, "needs_new_capability")

        proposal = self.validate_proposal(proposal)
        result = SelfDevelopmentExecutor(self.root).execute(proposal)
        return RepairAttempt(
            diagnosis,
            proposal,
            result,
            "candidate_repaired" if result.tests_passed and result.committed else "repair_failed_validation",
        )

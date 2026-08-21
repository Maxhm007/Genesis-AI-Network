from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .coding import CodingModule
from .file_self_review_policy import QuorumFileSelfReviewLoop
from .modules.task_queue import PersistentTaskQueue


AUTONOMOUS_REPAIR_EXCLUDED = {
    "genesis/autonomy_guard.py",
    "genesis/autonomy_proof.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/security.py",
    "genesis/selfdev.py",
    "genesis/file_self_review.py",
    "genesis/file_self_review_policy.py",
}


@dataclass(frozen=True)
class IssueDiscoveryCandidate:
    path: str
    score: int
    reasons: tuple[str, ...]
    test_path: str | None
    protected: bool


class GenesisIssueDiscoveryEngine:
    """Rank Genesis source by evidence and turn confirmed findings into durable work.

    Ranking is deterministic and evidence-led: error boundaries, state/IO,
    subprocess/network surfaces, missing tests, recent changes, and complexity
    matter more than file size. A non-bootstrap reasoning provider then confirms
    whether a high-risk file contains a concrete testable issue before a task is
    created. This engine never edits code or promotes candidates itself.
    """

    MAX_SOURCE_BYTES = 6_000
    MAX_TEST_BYTES = 3_000
    MAX_PROVIDER_FILES = 6
    MAX_RANKED_EVIDENCE = 20

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime" / "discovery"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.last_result_path = self.runtime / "last_result.json"
        self.history_path = self.runtime / "history.jsonl"

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=False)

    def _recent_change_score(self, path: str) -> tuple[int, str | None]:
        result = self._git("log", "-1", "--format=%ct", "--", path)
        if result.returncode != 0 or not result.stdout.strip().isdigit():
            return 0, None
        try:
            from time import time

            age_days = max(0.0, (time() - int(result.stdout.strip())) / 86400.0)
        except Exception:
            return 0, None
        if age_days <= 7:
            return 14, "changed_within_7_days"
        if age_days <= 30:
            return 9, "changed_within_30_days"
        if age_days <= 90:
            return 4, "changed_within_90_days"
        return 0, None

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        value = node.func
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            parts: list[str] = [value.attr]
            cursor = value.value
            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value
            if isinstance(cursor, ast.Name):
                parts.append(cursor.id)
            return ".".join(reversed(parts))
        return ""

    def _score_path(self, path: Path) -> IssueDiscoveryCandidate:
        relative = path.relative_to(self.root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        reasons: list[str] = []
        score = 0
        protected = relative in AUTONOMOUS_REPAIR_EXCLUDED
        test_path = f"tests/test_{path.stem}.py"
        conventional_test = self.root / test_path

        if not conventional_test.is_file():
            score += 14
            reasons.append("missing_conventional_test")

        lowered = text.lower()
        if "todo" in lowered or "fixme" in lowered:
            score += 10
            reasons.append("todo_or_fixme")
        if "notimplementederror" in lowered or "notimplemented" in lowered:
            score += 18
            reasons.append("incomplete_or_not_implemented")

        try:
            tree = ast.parse(text)
        except SyntaxError:
            score += 100
            reasons.append("syntax_error")
            tree = None

        if tree is not None:
            nodes = list(ast.walk(tree))
            branches = sum(isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.Match, ast.BoolOp)) for node in nodes)
            functions = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in nodes)
            broad_handlers = 0
            bare_handlers = 0
            calls: set[str] = set()
            for node in nodes:
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        bare_handlers += 1
                    elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                        broad_handlers += 1
                elif isinstance(node, ast.Call):
                    name = self._call_name(node)
                    if name:
                        calls.add(name)

            if bare_handlers:
                score += 28 + min(12, bare_handlers * 4)
                reasons.append("bare_exception_handler")
            if broad_handlers:
                score += 12 + min(12, broad_handlers * 3)
                reasons.append("broad_exception_handler")
            if any(name in calls for name in {"subprocess.run", "subprocess.Popen", "os.system"}):
                score += 18
                reasons.append("subprocess_or_shell_boundary")
            if any(name.startswith(("urllib.", "requests.", "socket.")) for name in calls):
                score += 16
                reasons.append("network_boundary")
            if any(name in calls for name in {"Path.write_text", "Path.write_bytes", "json.dump", "sqlite3.connect"}) or "sqlite3" in lowered:
                score += 13
                reasons.append("persistent_state_or_io")
            if "bool" in calls:
                score += 7
                reasons.append("explicit_bool_coercion")

            complexity = branches + functions
            if complexity >= 25:
                score += min(18, complexity // 4)
                reasons.append("high_branching_surface")
            elif complexity >= 12:
                score += min(10, complexity // 4)
                reasons.append("moderate_branching_surface")

        recent_score, recent_reason = self._recent_change_score(relative)
        score += recent_score
        if recent_reason:
            reasons.append(recent_reason)

        # File size is only a weak tie breaker; it is never the primary order.
        score += min(6, len(text.encode("utf-8")) // 5000)

        if protected:
            score = max(0, score - 35)
            reasons.append("protected_control_plane")

        return IssueDiscoveryCandidate(
            path=relative,
            score=int(score),
            reasons=tuple(dict.fromkeys(reasons)),
            test_path=test_path if conventional_test.is_file() else None,
            protected=protected,
        )

    def rank_candidates(self, *, include_protected: bool = False) -> list[IssueDiscoveryCandidate]:
        base = self.root / "genesis"
        if not base.is_dir():
            return []
        candidates: list[IssueDiscoveryCandidate] = []
        for path in base.rglob("*.py"):
            if not path.is_file() or "__pycache__" in path.parts or path.name == "__init__.py":
                continue
            candidate = self._score_path(path)
            if candidate.protected and not include_protected:
                continue
            candidates.append(candidate)
        candidates.sort(key=lambda item: (-item.score, item.path))
        return candidates

    def rank_paths(self, *, include_protected: bool = True) -> list[str]:
        return [candidate.path for candidate in self.rank_candidates(include_protected=include_protected)]

    @staticmethod
    def _confidence(value: object) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        text = str(value or "").strip().lower()
        return {"high": 0.85, "medium": 0.65, "low": 0.4}.get(text, 0.6)

    @staticmethod
    def _bounded_text(path: Path, max_bytes: int) -> str:
        return path.read_bytes()[:max_bytes].decode("utf-8", errors="replace")

    def _prompt(self, candidate: IssueDiscoveryCandidate) -> str:
        source = self._bounded_text(self.root / candidate.path, self.MAX_SOURCE_BYTES)
        tests = (
            self._bounded_text(self.root / candidate.test_path, self.MAX_TEST_BYTES)
            if candidate.test_path and (self.root / candidate.test_path).is_file()
            else "No conventional test file exists."
        )
        return (
            "ROLE: genesis_issue_discovery_engine\n"
            "Independently inspect this Genesis source file for one concrete, meaningful software issue. "
            "Use the supplied risk signals as hints, not proof. Look for correctness bugs, unsafe coercion, edge cases, "
            "state mistakes, error-handling defects, reliability failures, or testable autonomy defects. "
            "Do not invent style work, speculative refactoring, or changes that weaken tests, Security, validation, governance, "
            "protected boundaries, or promotion. Return compact JSON only with keys decision, summary, acceptance, evidence, confidence. "
            "decision must be issue or no_issue. If issue, summary must state observable incorrect behavior, acceptance must "
            "state the expected passing behavior without prescribing implementation, and evidence must be one short exact substring "
            "copied verbatim from SOURCE or RELATED_TEST_CONTEXT that directly supports the claim. If no exact supporting evidence "
            "can be quoted, return no_issue. Keep the entire response under 120 words.\n"
            f"TARGET: {candidate.path}\n"
            f"RISK_SCORE: {candidate.score}\n"
            f"RISK_SIGNALS: {', '.join(candidate.reasons) or 'none'}\n"
            f"SOURCE:\n{source}\n"
            f"RELATED_TEST_CONTEXT:\n{tests}\n"
        )

    @staticmethod
    def _parse(raw: str) -> dict:
        payload = CodingModule._extract_json(raw)
        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in {"issue", "no_issue"}:
            raise ValueError("discovery decision must be issue or no_issue")
        summary = str(payload.get("summary", "")).strip()
        acceptance = str(payload.get("acceptance", "")).strip()
        evidence = str(payload.get("evidence", "")).strip()
        if decision == "issue" and (not summary or not acceptance or not evidence):
            raise ValueError("issue discovery requires summary, acceptance, and exact evidence")
        return {
            "decision": decision,
            "summary": summary[:2400],
            "acceptance": acceptance[:3000],
            "evidence": evidence[:1000],
            "confidence": payload.get("confidence"),
        }

    def _ground_finding(self, candidate: IssueDiscoveryCandidate, finding: dict) -> tuple[bool, str | None]:
        if finding.get("decision") != "issue":
            return True, None
        source = self._bounded_text(self.root / candidate.path, self.MAX_SOURCE_BYTES)
        tests = (
            self._bounded_text(self.root / candidate.test_path, self.MAX_TEST_BYTES)
            if candidate.test_path and (self.root / candidate.test_path).is_file()
            else ""
        )
        evidence = str(finding.get("evidence") or "")
        if not evidence or (evidence not in source and evidence not in tests):
            return False, "evidence_not_found_in_supplied_context"

        claim = f"{finding.get('summary', '')} {finding.get('acceptance', '')}".lower()
        claims_syntax_failure = "syntax error" in claim or "syntaxerror" in claim
        if claims_syntax_failure and "syntax_error" not in candidate.reasons:
            return False, "syntax_claim_without_parser_evidence"
        return True, None

    def _persist(self, result: dict) -> None:
        self.last_result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, sort_keys=True) + "\n")

    def discover_and_enqueue(self, queue: PersistentTaskQueue, provider) -> dict:
        ranked = self.rank_candidates(include_protected=False)
        result: dict = {
            "status": "started",
            "ranked": [asdict(item) for item in ranked[: self.MAX_RANKED_EVIDENCE]],
            "scanned": [],
            "task_id": None,
            "target": None,
        }

        if provider is None or str(getattr(provider, "name", "")) == "genesis-bootstrap":
            result.update({"status": "blocked", "reason": "non_bootstrap_provider_required"})
            self._persist(result)
            return result

        for candidate in ranked[: self.MAX_PROVIDER_FILES]:
            try:
                finding = self._parse(provider.reason(self._prompt(candidate)))
            except Exception as exc:
                result["scanned"].append(
                    {
                        "target": candidate.path,
                        "score": candidate.score,
                        "status": "provider_error",
                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                    }
                )
                if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
                    break
                continue

            grounded, grounding_error = self._ground_finding(candidate, finding)
            confidence = self._confidence(finding.get("confidence"))
            scan = {
                "target": candidate.path,
                "score": candidate.score,
                "reasons": list(candidate.reasons),
                **finding,
                "confidence_normalized": confidence,
            }
            if not grounded:
                scan["status"] = "unsupported_finding"
                scan["grounding_error"] = grounding_error
                result["scanned"].append(scan)
                continue

            result["scanned"].append(scan)
            if finding["decision"] != "issue" or confidence < 0.55:
                continue

            source_sha = hashlib.sha256((self.root / candidate.path).read_bytes()).hexdigest()[:16]
            objective = (
                f"Autonomously repair a discovered Genesis issue in {candidate.path}. "
                f"Problem: {finding['summary']} Acceptance: {finding['acceptance']} "
                f"Grounding evidence: {finding['evidence']} "
                "Diagnose current repository evidence yourself and make the smallest correct change. "
                "Do not weaken tests, Security, validation, governance, or promotion safeguards."
            )
            context_paths = [candidate.path]
            if candidate.test_path:
                context_paths.append(candidate.test_path)
            priority = min(96, max(55, 58 + candidate.score // 3 + int(confidence * 12)))
            task, created = queue.create_unique(
                f"genesis-issue-discovery:{candidate.path}:{source_sha}",
                objective,
                module_id="genesis.coding",
                priority=priority,
                payload={
                    "source": "genesis.issue_discovery",
                    "task_type": "self_repair",
                    "target_path": candidate.path,
                    "context_paths": context_paths,
                    "discovery": scan,
                    "source_sha": source_sha,
                },
                max_attempts=4,
            )
            result.update(
                {
                    "status": "issue_enqueued" if created else "issue_already_known",
                    "task_id": task.task_id,
                    "target": candidate.path,
                    "priority": priority,
                    "finding": scan,
                }
            )
            self._persist(result)
            return result

        result["provider_error_count"] = sum(
            1 for scan in result["scanned"] if scan.get("status") == "provider_error"
        )
        result["unsupported_finding_count"] = sum(
            1 for scan in result["scanned"] if scan.get("status") == "unsupported_finding"
        )
        result["status"] = "no_issue_found"
        self._persist(result)
        return result


class DiscoveryFileSelfReviewLoop(QuorumFileSelfReviewLoop):
    """Periodic reviewer using the same evidence ranking as Gene Pulse discovery."""

    def __init__(self, root: Path, providers=None) -> None:
        self.issue_discovery = GenesisIssueDiscoveryEngine(root)
        super().__init__(root, providers)

    def _source_inventory(self) -> list[str]:
        return self.issue_discovery.rank_paths(include_protected=True)

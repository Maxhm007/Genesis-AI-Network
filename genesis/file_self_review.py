from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .autonomy_proof import AutonomyProofLedger
from .coding import CodingModule, CodingProposal
from .providers import ProviderRegistry


REVIEW_METHODS = (
    "correctness_and_edge_cases",
    "reliability_and_error_handling",
    "simplicity_and_duplication",
    "performance_and_resource_use",
    "testability_and_observability",
    "fresh_independent_approach",
)

# These files may be inspected, but ordinary file-review must not autonomously
# rewrite Genesis's trust/control plane.
REVIEW_ONLY_FILES = {
    "genesis/autonomy_guard.py",
    "genesis/security.py",
    "genesis/blockchain.py",
    "genesis/ephemeral_validator.py",
    "genesis/selfdev.py",
}


class FileSelfReviewLoop:
    """Persistent one-file-at-a-time Genesis self-review loop.

    The loop keeps a deterministic inventory, starts with the smallest source
    files, remembers the current file across hosted runs, snapshots the source
    into a durable lab directory, and asks Genesis for either a concrete useful
    improvement or an explicit no-change decision. Failed candidates do not
    release focus: the same file is retried with another review method on a
    later cycle. A file advances only after no-change review or after its exact
    candidate commit is observed on main.
    """

    STATE_VERSION = 1
    MAX_REVIEW_BYTES = 14_000
    MAX_REVIEW_ATTEMPTS = 3

    def __init__(self, root: Path, providers: ProviderRegistry | None = None) -> None:
        self.root = Path(root).resolve()
        self.runtime = self.root / "runtime" / "task_reviews"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runtime / "file_self_review_state.json"
        self.lab_root = self.runtime / "file_self_review_lab"
        self.lab_root.mkdir(parents=True, exist_ok=True)
        self.providers = providers or ProviderRegistry()
        self.coding = CodingModule(self.root, self.providers)
        self.proof = AutonomyProofLedger(self.root)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True, check=False)

    def _source_inventory(self) -> list[str]:
        rows: list[tuple[int, str]] = []
        base = self.root / "genesis"
        if not base.is_dir():
            return []
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            if relative.endswith("/__init__.py") or relative == "genesis/__init__.py":
                continue
            rows.append((path.stat().st_size, relative))
        rows.sort(key=lambda item: (item[0], item[1]))
        return [relative for _, relative in rows]

    def _default_state(self) -> dict:
        return {
            "version": self.STATE_VERSION,
            "inventory": self._source_inventory(),
            "cursor": 0,
            "current": None,
            "reviewed": {},
            "updated_at": self._now(),
        }

    def _load(self) -> dict:
        if not self.state_path.is_file():
            return self._default_state()
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        current_inventory = self._source_inventory()
        inventory = [path for path in state.get("inventory", []) if path in current_inventory]
        inventory.extend(path for path in current_inventory if path not in inventory)
        state["inventory"] = inventory
        state.setdefault("cursor", 0)
        state.setdefault("current", None)
        state.setdefault("reviewed", {})
        return state

    def _save(self, state: dict) -> None:
        state["updated_at"] = self._now()
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _advance(self, state: dict, outcome: dict) -> None:
        current = state.get("current") or {}
        path = current.get("path")
        if path:
            state.setdefault("reviewed", {})[path] = outcome
        state["cursor"] = min(int(state.get("cursor", 0)) + 1, len(state.get("inventory", [])))
        state["current"] = None
        self._save(state)

    def _candidate_promoted(self, commit_sha: str) -> bool:
        if not commit_sha:
            return False
        return self._git("merge-base", "--is-ancestor", commit_sha, "HEAD").returncode == 0

    def _reconcile(self, state: dict) -> dict:
        current = state.get("current") or {}
        if current.get("status") != "waiting_validation":
            return state
        commit_sha = str(current.get("candidate_sha") or "")
        if self._candidate_promoted(commit_sha):
            cycle_id = str(current.get("cycle_id") or "")
            self.proof.record(
                cycle_id=cycle_id,
                stage="promotion_confirmed",
                actor="genesis.file_self_review",
                outcome="success",
                details={"path": current.get("path"), "commit_sha": commit_sha, "improvement": current.get("improvement")},
            )
            self.proof.record(
                cycle_id=cycle_id,
                stage="cycle_complete",
                actor="genesis.file_self_review",
                outcome="success",
                details={"path": current.get("path"), "promotion_confirmed": True, "improvement": current.get("improvement")},
            )
            self._advance(
                state,
                {
                    "status": "improved_and_promoted",
                    "reviewed_at": self._now(),
                    "improvement": current.get("improvement"),
                    "candidate_sha": commit_sha,
                    "attempts": current.get("attempts", 0),
                },
            )
            return self._load()

        # The previous workflow has finished before a new proactive cycle can
        # begin. If the commit is not on main, keep the same file and change
        # method instead of silently moving on.
        current["status"] = "retry"
        current["attempts"] = int(current.get("attempts", 0)) + 1
        current["method_index"] = (int(current.get("method_index", 0)) + 1) % len(REVIEW_METHODS)
        current["last_error"] = "previous candidate was not promoted"
        current.pop("candidate_sha", None)
        current.pop("candidate_branch", None)
        state["current"] = current
        self._save(state)
        return state

    def _ensure_current(self, state: dict) -> dict | None:
        current = state.get("current")
        if current:
            return current
        inventory = state.get("inventory", [])
        cursor = int(state.get("cursor", 0))
        if cursor >= len(inventory):
            # Start a new review generation so changed/new files can be examined
            # again without losing historical results.
            state["inventory"] = self._source_inventory()
            state["cursor"] = 0
            cursor = 0
            inventory = state["inventory"]
            if not inventory:
                self._save(state)
                return None
        path = inventory[cursor]
        current = {
            "path": path,
            "status": "reviewing",
            "method_index": 0,
            "attempts": 0,
            "started_at": self._now(),
            "review_only": path in REVIEW_ONLY_FILES,
        }
        state["current"] = current
        self._save(state)
        return current

    def _lab_snapshot(self, path: str, method: str) -> Path:
        source = self.root / path
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        lab = self.lab_root / f"{digest}-{Path(path).stem}"
        lab.mkdir(parents=True, exist_ok=True)
        (lab / "original.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        (lab / "meta.json").write_text(
            json.dumps({"source": path, "method": method, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return lab

    def _review_prompt(self, path: str, method: str, previous_error: str = "") -> str:
        source = (self.root / path).read_text(encoding="utf-8")
        source = source[: self.MAX_REVIEW_BYTES]
        return (
            "ROLE: genesis_self_reviewer\n"
            "Review exactly one of your own source files. Do not invent work merely to make a change.\n"
            f"FILE: {path}\nMETHOD: {method}\n"
            "Look for a concrete correctness bug, edge case, reliability weakness, unnecessary complexity, performance/resource issue, "
            "testability/observability weakness, or a clear autonomy improvement.\n"
            "If no meaningful improvement is justified by the source, choose no_change.\n"
            "Return JSON only with keys decision, summary, objective, confidence. decision must be improve or no_change.\n"
            f"PREVIOUS_FAILURE: {previous_error[:1500]}\n"
            f"SOURCE:\n{source}\n"
        )

    def _review(self, provider, path: str, method: str, previous_error: str = "") -> dict:
        prompt = self._review_prompt(path, method, previous_error)
        last_error: Exception | None = None
        for _ in range(self.MAX_REVIEW_ATTEMPTS):
            raw = provider.reason(prompt)
            try:
                payload = CodingModule._extract_json(raw)
                decision = str(payload.get("decision", "")).strip().lower()
                if decision not in {"improve", "no_change"}:
                    raise ValueError("review decision must be improve or no_change")
                return {
                    "decision": decision,
                    "summary": str(payload.get("summary", ""))[:2000],
                    "objective": str(payload.get("objective", ""))[:3000],
                    "confidence": payload.get("confidence"),
                }
            except Exception as exc:
                last_error = exc
                prompt += f"\nRETRY_ERROR: {type(exc).__name__}: {str(exc)[:500]}\nReturn one complete JSON object only."
        raise RuntimeError(f"file review provider failed: {last_error}")

    @staticmethod
    def _test_path(path: str) -> str:
        stem = Path(path).stem
        return f"tests/test_{stem}.py"

    def plan_next(self) -> dict | None:
        state = self._reconcile(self._load())
        current = self._ensure_current(state)
        if current is None:
            return None
        if current.get("status") == "waiting_validation":
            return None

        path = str(current["path"])
        method_index = int(current.get("method_index", 0)) % len(REVIEW_METHODS)
        method = REVIEW_METHODS[method_index]
        provider = self.coding._provider()
        if provider is None:
            current["status"] = "retry"
            current["last_error"] = "no intelligence provider available"
            state["current"] = current
            self._save(state)
            return None

        lab = self._lab_snapshot(path, method)
        try:
            review = self._review(provider, path, method, str(current.get("last_error") or ""))
        except Exception as exc:
            current["status"] = "retry"
            current["attempts"] = int(current.get("attempts", 0)) + 1
            current["method_index"] = (method_index + 1) % len(REVIEW_METHODS)
            current["last_error"] = f"{type(exc).__name__}: {exc}"[:1500]
            state["current"] = current
            self._save(state)
            return None

        current["review"] = review
        current["lab"] = str(lab.relative_to(self.root))
        if review["decision"] == "no_change":
            self._advance(
                state,
                {
                    "status": "reviewed_no_change",
                    "reviewed_at": self._now(),
                    "method": method,
                    "summary": review["summary"],
                    "confidence": review.get("confidence"),
                },
            )
            return None

        if current.get("review_only"):
            self._advance(
                state,
                {
                    "status": "reviewed_risk_escalation",
                    "reviewed_at": self._now(),
                    "method": method,
                    "summary": review["summary"],
                    "objective": review["objective"],
                    "owner_or_privileged_review_required": True,
                },
            )
            return None

        objective = (
            f"SELF_FILE_REVIEW: Improve only {path}. Genesis independently reviewed this file using method {method}. "
            f"Finding: {review['summary']} Objective: {review['objective']} "
            "Make the smallest behavior-preserving or correctness-improving edit justified by this finding. Do not edit any other file."
        )
        context = [path]
        test_path = self._test_path(path)
        if (self.root / test_path).is_file():
            context.append(test_path)
        try:
            proposal: CodingProposal = self.coding.propose(objective, context_paths=context, provider=provider)
        except Exception as exc:
            current["status"] = "retry"
            current["attempts"] = int(current.get("attempts", 0)) + 1
            current["method_index"] = (method_index + 1) % len(REVIEW_METHODS)
            current["last_error"] = f"coding proposal failed: {type(exc).__name__}: {exc}"[:1500]
            state["current"] = current
            self._save(state)
            return None

        if set(proposal.files) != {path}:
            current["status"] = "retry"
            current["attempts"] = int(current.get("attempts", 0)) + 1
            current["method_index"] = (method_index + 1) % len(REVIEW_METHODS)
            current["last_error"] = "proposal attempted to change a file outside the current self-review target"
            state["current"] = current
            self._save(state)
            return None

        (lab / "candidate.py").write_text(proposal.files[path], encoding="utf-8")
        cycle_id = hashlib.sha256(f"file-review|{path}|{self._now()}".encode("utf-8")).hexdigest()[:12]
        current.update(
            {
                "status": "candidate_planned",
                "method": method,
                "cycle_id": cycle_id,
                "improvement": review["summary"] or review["objective"],
            }
        )
        state["current"] = current
        self._save(state)
        self.proof.record(
            cycle_id=cycle_id,
            stage="discovery",
            actor="genesis.file_self_review",
            outcome="started",
            details={"title": review["summary"], "files": [path], "method": method, "lab": str(lab.relative_to(self.root))},
        )
        self.proof.record(
            cycle_id=cycle_id,
            stage="design",
            actor="genesis.file_self_review",
            outcome="ready",
            details={"objective": review["objective"], "target_file": path},
        )
        return {
            "title": f"Genesis file self-review: {path}",
            "rationale": review["summary"] or review["objective"],
            "proposal": {
                "title": f"Review improvement for {path}",
                "rationale": proposal.rationale,
                "files": proposal.files,
                "provenance": {
                    "initiator": "genesis.file_self_review",
                    "discovery": "genesis.file_self_review",
                    "designer": "genesis.file_self_review",
                },
                "file_self_review": {"path": path, "method": method, "cycle_id": cycle_id},
            },
        }

    def observe_execution(self, proposal: dict, result) -> None:
        meta = dict(proposal.get("file_self_review", {}) or {})
        if not meta:
            return
        state = self._load()
        current = state.get("current") or {}
        if current.get("path") != meta.get("path"):
            return
        if result.tests_passed and result.committed and result.commit_sha:
            current.update(
                {
                    "status": "waiting_validation",
                    "candidate_sha": result.commit_sha,
                    "candidate_branch": result.branch,
                    "cycle_id": meta.get("cycle_id") or current.get("cycle_id"),
                }
            )
            state["current"] = current
            self._save(state)
            return
        current["status"] = "retry"
        current["attempts"] = int(current.get("attempts", 0)) + 1
        current["method_index"] = (int(current.get("method_index", 0)) + 1) % len(REVIEW_METHODS)
        current["last_error"] = str(result.message or "candidate failed")[-2000:]
        state["current"] = current
        self._save(state)

    def status(self) -> dict:
        state = self._reconcile(self._load())
        return {
            "inventory_size": len(state.get("inventory", [])),
            "cursor": state.get("cursor", 0),
            "current": state.get("current"),
            "reviewed_count": len(state.get("reviewed", {})),
            "state_path": str(self.state_path.relative_to(self.root)),
            "lab_path": str(self.lab_root.relative_to(self.root)),
            "methods": list(REVIEW_METHODS),
        }

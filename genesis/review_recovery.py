from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from .autonomy_pipeline import DEVELOPMENT_SOURCE, PipelineStore
from .bounded_autonomy_pipeline import BoundedAutonomyPipelineCoordinator
from .issue_discovery import AUTONOMOUS_REPAIR_EXCLUDED


INSTALL_MARKER = "_genesis_orphan_review_recovery_installed"
REVIEW_REF_RE = re.compile(r"^genesis/review-([0-9a-f]{12})$")
GENESIS_CANDIDATE_PREFIX = "Genesis self-development candidate:"
GENESIS_AUTHOR_EMAIL = "genesis-ai@users.noreply.github.com"
LEARNED_CAPABILITY_TARGET = "genesis/learned_capabilities.py"
_ORIGINAL_RUN_ONCE = BoundedAutonomyPipelineCoordinator.run_once


def _git(root: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )


def _review_refs(root: Path) -> list[tuple[str, str]]:
    """Return surviving Genesis review refs and exact candidate SHAs."""
    _git(
        root,
        "fetch",
        "origin",
        "+refs/heads/genesis/review-*:refs/remotes/origin/genesis/review-*",
    )
    result = _git(
        root,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/remotes/origin/genesis/review-",
    )
    if result.returncode != 0:
        return []
    refs: list[tuple[str, str]] = []
    prefix = "refs/remotes/origin/"
    for line in result.stdout.splitlines():
        raw = line.strip().split()
        if len(raw) != 2 or not raw[0].startswith(prefix):
            continue
        ref = raw[0][len(prefix) :]
        sha = raw[1].lower()
        match = REVIEW_REF_RE.fullmatch(ref)
        if not match or not sha.startswith(match.group(1)):
            continue
        refs.append((ref, sha))
    return sorted(refs)


def _changed_files(root: Path, sha: str) -> list[str]:
    result = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", f"{sha}^", sha)
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/").lstrip("./") for line in result.stdout.splitlines() if line.strip()]


def _show_file(root: Path, ref: str, path: str) -> str:
    result = _git(root, "show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else ""


def _learned_capability_metadata(root: Path, sha: str) -> dict:
    """Recover grounded metadata already embedded in a learned-capability candidate."""
    candidate = _show_file(root, sha, LEARNED_CAPABILITY_TARGET)
    current = _show_file(root, "origin/main", LEARNED_CAPABILITY_TARGET)
    if not candidate:
        return {}

    def registrations(source: str) -> dict[str, tuple[str, str]]:
        if not source:
            return {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        found: dict[str, tuple[str, str]] = {}
        for node in tree.body:
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not isinstance(call.func, ast.Name) or call.func.id != "register_capability":
                continue
            if len(call.args) < 3:
                continue
            values: list[str] = []
            for arg in call.args[:3]:
                if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                    values = []
                    break
                values.append(arg.value.strip())
            if len(values) == 3 and all(values):
                found[values[0]] = (values[1], values[2])
        return found

    before = registrations(current)
    after = registrations(candidate)
    added = [(name, *values) for name, values in after.items() if name not in before]
    if len(added) != 1:
        return {}
    name, description, evidence = added[0]
    return {
        "capability_key": name,
        "lesson": description[:1000],
        "lesson_evidence": evidence[:1200],
        "learning_evidence": evidence[:1200],
        "summary": description[:2400],
        "acceptance": (
            "Recovered Genesis candidate must preserve one bounded registered capability, "
            "pass the full test suite, pass internal review, and pass independent validation before promotion."
        ),
        "new_capability": True,
        "grounded": True,
    }


def _candidate_evidence(root: Path, ref: str, sha: str) -> dict | None:
    subject_result = _git(root, "show", "-s", "--format=%s", sha)
    email_result = _git(root, "show", "-s", "--format=%ae", sha)
    if subject_result.returncode != 0 or email_result.returncode != 0:
        return None
    subject = subject_result.stdout.strip()
    author_email = email_result.stdout.strip().lower()
    if not subject.startswith(GENESIS_CANDIDATE_PREFIX):
        return None
    if author_email != GENESIS_AUTHOR_EMAIL:
        return None

    files = _changed_files(root, sha)
    if len(files) != 1:
        return None
    target = files[0]
    if target in AUTONOMOUS_REPAIR_EXCLUDED:
        return None
    if not _show_file(root, sha, target):
        return None

    # Do not recover work that is already present on main, including an equivalent
    # patch rebased by the normal candidate-promotion workflow.
    _git(root, "fetch", "origin", "main")
    ancestor = _git(root, "merge-base", "--is-ancestor", sha, "origin/main")
    if ancestor.returncode == 0:
        return None
    cherry = _git(root, "cherry", "origin/main", sha)
    lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
    if lines and all(line.startswith("-") for line in lines):
        return None

    patch = _git(root, "diff", f"{sha}^", sha, "--", target).stdout
    if not patch.strip():
        return None
    applies = _git(root, "apply", "--check", "-", input_text=patch)
    if applies.returncode != 0:
        return None

    finding: dict = {
        "summary": subject[len(GENESIS_CANDIDATE_PREFIX) :].strip()[:2400],
        "confidence_normalized": 1.0,
        "grounded": True,
    }
    source = "genesis.review_recovery"
    task_type = "recovered_review"
    capability_key = ""
    if target == LEARNED_CAPABILITY_TARGET:
        learned = _learned_capability_metadata(root, sha)
        if not learned:
            return None
        finding.update(learned)
        source = DEVELOPMENT_SOURCE
        task_type = "new_capability"
        capability_key = str(learned["capability_key"])

    return {
        "ref": ref,
        "sha": sha,
        "subject": subject,
        "target": target,
        "source": source,
        "task_type": task_type,
        "capability_key": capability_key,
        "finding": finding,
    }


def recover_one_orphan_review(root: Path, coordinator: BoundedAutonomyPipelineCoordinator) -> dict | None:
    """Reconstruct one missing review task from surviving Git evidence.

    Git review refs outlive Actions caches. Recovery never approves or promotes a
    candidate; it only restores queue/pipeline metadata so the normal reviewer and
    independent validation gates can resume.
    """
    root = Path(root).resolve()
    if coordinator.store.list_active():
        return None

    for ref, sha in _review_refs(root):
        evidence = _candidate_evidence(root, ref, sha)
        if not evidence:
            continue
        target = str(evidence["target"])
        finding = dict(evidence["finding"])
        source = str(evidence["source"])
        payload = {
            "source": source,
            "task_type": evidence["task_type"],
            "target_path": target,
            "context_paths": [target],
            "recovered_review_ref": ref,
            "recovered_candidate_sha": sha,
            "discovery": {"finding": finding},
        }
        if evidence.get("capability_key"):
            payload["capability_key"] = evidence["capability_key"]

        task, _created = coordinator.engineering.queue.create_unique(
            f"genesis-orphan-review-recovery:{sha}",
            (
                f"Resume Genesis-owned candidate {sha} for {target}. "
                "Do not broaden the candidate. Re-run full tests, internal review, independent validation, "
                "and promotion gates before accepting it."
            ),
            module_id="genesis.coding",
            priority=95,
            payload=payload,
            max_attempts=4,
        )
        if task.state in {"complete", "cancelled", "quarantined"}:
            continue
        if task.state in {"failed", "blocked", "paused"}:
            task = coordinator.engineering.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
        if task.state == "new":
            task = coordinator.engineering.queue.transition(task.task_id, "assigned", module_id="genesis.coding")
        if task.state == "assigned":
            task = coordinator.engineering.queue.transition(task.task_id, "running", module_id="genesis.coding")
        if task.state == "running":
            task = coordinator.engineering.queue.transition(task.task_id, "review", module_id="genesis.coding")
        if task.state != "review":
            continue

        discovery = {
            "status": "orphan_review_recovered",
            "source": source,
            "task_id": task.task_id,
            "target": target,
            "candidate_sha": sha,
            "review_ref": ref,
            "finding": finding,
        }
        existing = coordinator.store.get(task.task_id)
        if existing is None:
            coordinator.store.register_discovery(task.task_id, target, discovery)
        coordinator.store.transition(
            task.task_id,
            "review_ready",
            worker="review_recovery",
            candidate_branch=f"genesis/candidate-{sha[:12]}",
            candidate_sha=sha,
            review_ref=ref,
        )
        return discovery
    return None


def _run_once_with_orphan_recovery(self: BoundedAutonomyPipelineCoordinator):
    recovered = recover_one_orphan_review(self.root, self)
    result = _ORIGINAL_RUN_ONCE(self)
    if recovered:
        result = dict(result)
        result["orphan_review_recovery"] = recovered
    return result


def install_orphan_review_recovery() -> None:
    if getattr(BoundedAutonomyPipelineCoordinator, INSTALL_MARKER, False):
        return
    BoundedAutonomyPipelineCoordinator.run_once = _run_once_with_orphan_recovery
    setattr(BoundedAutonomyPipelineCoordinator, INSTALL_MARKER, True)

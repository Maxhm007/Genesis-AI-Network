from __future__ import annotations

import hashlib
import ast
import re
from dataclasses import dataclass
from pathlib import Path


def validate_architecture_source(source: str) -> None:
    """Reject non-executable scaffolds before they can become trusted modules."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"architecture module syntax is invalid: {exc.msg}") from exc
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not functions:
        raise ValueError("architecture module must implement a callable capability")
    def operations_without_raises(node):
        if isinstance(node, ast.Raise):
            return []
        return [node, *(child for item in ast.iter_child_nodes(node) for child in operations_without_raises(item))]
    for function in functions:
        operations = [node for statement in function.body for node in operations_without_raises(statement)]
        if not any(
            isinstance(node, (ast.Call, ast.Assign, ast.AugAssign))
            or (isinstance(node, ast.Return) and node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None))
            for node in operations
        ):
            raise ValueError("architecture callable has no implemented behavior")
    for node in ast.walk(tree):
        if isinstance(node, ast.Pass) or (isinstance(node, ast.Constant) and node.value is Ellipsis):
            raise ValueError("architecture module contains a placeholder")
        if isinstance(node, ast.Name) and node.id == "NotImplementedError":
            raise ValueError("architecture module contains an unimplemented capability")


@dataclass(frozen=True)
class ArchitecturePlan:
    primary_target: str
    integration_target: str = ""
    reason: str = ""

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(path for path in (self.primary_target, self.integration_target) if path)

    @property
    def requires_new_file(self) -> bool:
        return self.primary_target.startswith("genesis/architecture_extensions/")


def _text(issue: dict) -> str:
    return f"{issue.get('title') or ''}\n{issue.get('body') or ''}".lower()


def _safe_existing(root: Path, relative: str) -> bool:
    path = str(relative or "").replace("\\", "/").lstrip("./")
    return (
        path.startswith(("genesis/", "scripts/"))
        and path.endswith(".py")
        and ".." not in Path(path).parts
        and (Path(root) / path).is_file()
    )


def _new_extension_path(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    slug = slug[:64].strip("_") or "architecture_extension"
    return f"genesis/architecture_extensions/{slug}.py"


def plan_fingerprint(plan: ArchitecturePlan) -> str:
    raw = "|".join(plan.targets).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def build_architecture_plan(issue: dict, root: Path) -> ArchitecturePlan | None:
    """Return a bounded implementation plan from architecture semantics.

    Existing authoritative modules are preferred. A new module is proposed only
    for responsibilities with no suitable existing implementation surface, and
    then exactly one existing integration surface is required as the second step.
    """
    root = Path(root).resolve()
    title_text = str(issue.get("title") or "").lower()
    full_text = _text(issue)

    mappings = (
        (("stale", "pull request"), "genesis/architecture_extensions/pull_request_maintenance.py", "genesis/github_issue_cleanup.py", "pull_request_maintenance"),
        (("backlog", "governor"), "genesis/issue_governor.py", "", "backlog_governor"),
        (("issue", "value", "score"), "genesis/issue_governor.py", "", "issue_value_scoring"),
        (("workflow", "governance"), "genesis/workflow_governor.py", "", "workflow_governance"),
        (("workflow", "retire"), "genesis/workflow_governor.py", "", "workflow_governance"),
        (("least-privilege", "credential"), "genesis/capability_routing.py", "", "least_privilege_capability_routing"),
        (("least privilege", "credential"), "genesis/capability_routing.py", "", "least_privilege_capability_routing"),
        (("autonomous", "system", "health", "closure", "velocity"), "genesis/architecture_extensions/autonomous_system_health_controller.py", "genesis/health.py", "autonomous_system_health_observability"),
        (("health", "dashboard"), "genesis/health.py", "", "health_observability"),
        (("model", "specialization"), "genesis/intelligence_router.py", "", "model_specialization"),
        (("task-to-model", "routing"), "genesis/intelligence_router.py", "", "model_specialization"),
        (("stuck", "strategy"), "genesis/anti_stuck.py", "", "adaptive_recovery"),
        (("issue splitting",), "genesis/anti_stuck.py", "", "adaptive_recovery"),
    )

    for corpus in (title_text, full_text):
        for terms, primary, integration, reason in mappings:
            if not all(term in corpus for term in terms):
                continue
            if primary.startswith("genesis/architecture_extensions/"):
                if not _safe_existing(root, integration):
                    return None
                return ArchitecturePlan(primary, integration, reason)
            if _safe_existing(root, primary):
                return ArchitecturePlan(primary, "", reason)
            return None

    return None

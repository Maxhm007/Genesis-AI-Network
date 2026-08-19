from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass(frozen=True)
class GeneWorker:
    gene: str
    logical_id: str
    repository: str
    role: str
    model: str
    license: str
    capabilities: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


class GeneComputeFabric:
    """Load Gene worker/model assignments and select a peer for a routed task.

    Gene 0 remains the coordinator. Worker model names are replaceable runtime
    configuration and are never treated as Gene identity.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.path = self.root / "config" / "gene_compute.json"
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.coordinator = dict(payload["coordinator"])
        self.rules = dict(payload.get("rules") or {})
        self.workers = tuple(
            GeneWorker(
                gene=str(row["gene"]),
                logical_id=str(row["logical_id"]),
                repository=str(row["repository"]),
                role=str(row["role"]),
                model=str(row["model"]),
                license=str(row["license"]),
                capabilities=tuple(str(value) for value in row.get("capabilities", [])),
            )
            for row in payload.get("workers", [])
        )

    @staticmethod
    def _required_capability(module_id: str | None, objective: str) -> str:
        module = (module_id or "").lower()
        text = objective.lower()
        if "coding" in module or any(word in text for word in ("code", "bug", "repair", "fix", "engineering")):
            return "engineering"
        if "research" in module or any(word in text for word in ("research", "paper", "study", "evidence")):
            return "research"
        if "security" in module or "validation" in module or any(word in text for word in ("validate", "review", "challenge")):
            return "validation"
        return "reasoning"

    def select(self, module_id: str | None, objective: str) -> GeneWorker | None:
        capability = self._required_capability(module_id, objective)
        candidates = [worker for worker in self.workers if capability in worker.capabilities]
        if not candidates and capability == "engineering":
            candidates = [worker for worker in self.workers if "coding" in worker.capabilities]
        if not candidates:
            candidates = [worker for worker in self.workers if "reasoning" in worker.capabilities]
        if not candidates:
            return None
        # Stable role specialization: research/validation -> Gene 2, engineering -> Gene 3.
        candidates.sort(key=lambda worker: (worker.logical_id, worker.model))
        if capability in {"engineering", "coding", "repair"}:
            for worker in candidates:
                if worker.logical_id == "gene-node-3":
                    return worker
        if capability in {"research", "validation", "review"}:
            for worker in candidates:
                if worker.logical_id == "gene-node-2":
                    return worker
        return candidates[0]

    def topology(self) -> dict:
        return {
            "coordinator": self.coordinator,
            "workers": [worker.as_dict() for worker in self.workers],
            "rules": self.rules,
        }

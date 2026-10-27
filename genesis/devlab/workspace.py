from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class LabSnapshot:
    source_path: str
    source_sha256: str
    snapshot_path: str


@dataclass(frozen=True)
class EditProposal:
    target_path: str
    content: str
    rationale: str = ""


class LabWorkspace:
    """Create isolated, auditable copies of repository files for DevLab work."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.lab_root = self.root / "runtime" / "task_reviews" / "devlab"
        self.lab_root.mkdir(parents=True, exist_ok=True)

    def resolve_source(self, relative: str) -> Path:
        normalized = str(relative).replace("\\", "/").lstrip("./")
        path = (self.root / normalized).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("DevLab source path escapes repository root") from exc
        if not path.is_file():
            raise FileNotFoundError(normalized)
        return path

    def read(self, relative: str) -> str:
        return self.resolve_source(relative).read_text(encoding="utf-8")

    def snapshot(self, relative: str) -> LabSnapshot:
        source = self.resolve_source(relative)
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        session = self.lab_root / f"{stamp}-{digest[:10]}"
        destination = session / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return LabSnapshot(
            source_path=str(source.relative_to(self.root)).replace("\\", "/"),
            source_sha256=digest,
            snapshot_path=str(destination.relative_to(self.root)).replace("\\", "/"),
        )

    def write_lab_candidate(self, snapshot: LabSnapshot, content: str) -> str:
        snapshot_path = self.root / snapshot.snapshot_path
        candidate_path = snapshot_path.parent / f"{snapshot_path.name}.candidate"
        candidate_path.write_text(content, encoding="utf-8")
        return str(candidate_path.relative_to(self.root)).replace("\\", "/")

    @staticmethod
    def validate_edit(proposal: EditProposal, expected_target: str) -> None:
        normalized = proposal.target_path.replace("\\", "/").lstrip("./")
        expected = expected_target.replace("\\", "/").lstrip("./")
        if normalized != expected:
            raise ValueError("DevLab edit must target exactly the assigned file")
        if not proposal.content.strip():
            raise ValueError("DevLab candidate content must not be empty")

    def stage_edit(self, snapshot: LabSnapshot, proposal: EditProposal) -> str:
        self.validate_edit(proposal, snapshot.source_path)
        return self.write_lab_candidate(snapshot, proposal.content)

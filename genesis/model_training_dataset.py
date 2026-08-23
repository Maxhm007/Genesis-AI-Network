from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
OUTPUT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.jsonl$")
GENESIS_AUTHOR = ("Genesis AI", "genesis-ai@users.noreply.github.com")
GENESIS_COMMITTER = ("Genesis Promotion Stager", "genesis-promotion@users.noreply.github.com")
GENESIS_MESSAGE_PREFIX = "Genesis self-development candidate:"
VALIDATION_PRODUCER = "genesis-independent-validator-gate"
VALIDATION_PAYLOAD_TYPE = "validated_update"
MAX_PATCH_BYTES = 256 * 1024
MAX_EXAMPLES = 10_000
POLICY_VERSION = "genesis-validated-autonomous-code-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class DatasetCollection:
    examples: tuple[dict[str, Any], ...]
    included_commits: tuple[str, ...]
    excluded_by_reason: dict[str, int]
    head_commit: str
    blockchain_sha256: str


class GenesisTrainingDatasetBuilder:
    """Build SFT data only from independently validated Genesis-owned promotions.

    This deliberately excludes owner/assistant PRs, unvalidated Genesis branches,
    failed candidates, workflow/config changes and arbitrary repository history.
    Eligibility is the intersection of current-main ancestry, the independent
    validator blockchain ledger and the exact identities used by the autonomous
    promotion stager.

    The produced JSONL remains a *training input*, not evidence that a model has
    been trained or improved. Benchmarking and Model Lab promotion stay separate.
    """

    def __init__(
        self,
        root: Path,
        *,
        blockchain_path: Path | None = None,
        output_root: Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.blockchain_path = (
            Path(blockchain_path).resolve()
            if blockchain_path is not None
            else (self.root / "network" / "blockchain.jsonl").resolve()
        )
        self.output_root = (
            Path(output_root).resolve()
            if output_root is not None
            else (self.root / "runtime" / "model_datasets").resolve()
        )
        self._require_inside(self.blockchain_path, self.root, "blockchain path")
        self._require_inside(self.output_root, self.root, "dataset output root")

    @staticmethod
    def _require_inside(path: Path, parent: Path, label: str) -> None:
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise ValueError(f"{label} must stay inside the Genesis repository") from exc

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and completed.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed with exit {completed.returncode}: {completed.stderr[-2000:]}"
            )
        return completed

    def _resolve_head(self, head: str) -> str:
        raw = str(head or "HEAD").strip() or "HEAD"
        completed = self._git("rev-parse", "--verify", f"{raw}^{{commit}}")
        value = completed.stdout.strip().lower()
        if not COMMIT_RE.fullmatch(value):
            raise RuntimeError("could not resolve a full Git commit for dataset head")
        return value

    def _load_validation_rows(self) -> list[dict[str, Any]]:
        if not self.blockchain_path.is_file():
            raise FileNotFoundError(self.blockchain_path)
        rows: list[dict[str, Any]] = []
        for line_number, raw in enumerate(self.blockchain_path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"blockchain line {line_number} is not valid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"blockchain line {line_number} must be an object")
            rows.append(row)
        if not rows:
            raise ValueError("independent validation blockchain contains no records")
        return rows

    def _is_ancestor(self, commit: str, head: str) -> bool:
        completed = self._git("merge-base", "--is-ancestor", commit, head, check=False)
        if completed.returncode == 0:
            return True
        if completed.returncode == 1:
            return False
        return False

    def _commit_metadata(self, commit: str) -> dict[str, str] | None:
        completed = self._git(
            "show",
            "-s",
            "--format=%an%x00%ae%x00%cn%x00%ce%x00%B",
            commit,
            check=False,
        )
        if completed.returncode != 0:
            return None
        parts = completed.stdout.split("\x00", 4)
        if len(parts) != 5:
            return None
        return {
            "author_name": parts[0].strip(),
            "author_email": parts[1].strip(),
            "committer_name": parts[2].strip(),
            "committer_email": parts[3].strip(),
            "message": parts[4].strip(),
        }

    def _changed_files(self, commit: str) -> tuple[str, ...]:
        completed = self._git(
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
        )
        return tuple(sorted({line.strip() for line in completed.stdout.splitlines() if line.strip()}))

    @staticmethod
    def _safe_code_paths(paths: tuple[str, ...]) -> bool:
        if not paths:
            return False
        has_genesis_source = False
        for raw in paths:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                return False
            normalized = path.as_posix()
            if normalized.startswith("genesis/") and normalized.endswith(".py"):
                has_genesis_source = True
                continue
            if normalized.startswith("tests/") and normalized.endswith(".py"):
                continue
            return False
        return has_genesis_source

    def _patch(self, commit: str) -> str | None:
        completed = self._git(
            "show",
            "--format=",
            "--no-color",
            "--no-ext-diff",
            "--unified=3",
            commit,
            "--",
            "genesis",
            "tests",
            check=False,
        )
        if completed.returncode != 0:
            return None
        patch = completed.stdout.strip()
        encoded = patch.encode("utf-8")
        if not patch or len(encoded) > MAX_PATCH_BYTES:
            return None
        return patch

    @staticmethod
    def _increment(bucket: dict[str, int], reason: str) -> None:
        bucket[reason] = bucket.get(reason, 0) + 1

    def collect(self, *, head: str = "HEAD", max_examples: int = MAX_EXAMPLES) -> DatasetCollection:
        if isinstance(max_examples, bool) or not isinstance(max_examples, int) or not 1 <= max_examples <= MAX_EXAMPLES:
            raise ValueError(f"max_examples must be between 1 and {MAX_EXAMPLES}")

        head_commit = self._resolve_head(head)
        rows = self._load_validation_rows()
        blockchain_hash = sha256_file(self.blockchain_path)
        excluded: dict[str, int] = {}
        seen: set[str] = set()
        examples: list[dict[str, Any]] = []
        included: list[str] = []

        for row in rows:
            if row.get("payload_type") != VALIDATION_PAYLOAD_TYPE or row.get("producer") != VALIDATION_PRODUCER:
                self._increment(excluded, "not_independent_validator_record")
                continue

            commit = str(row.get("validated_commit") or "").strip().lower()
            if not COMMIT_RE.fullmatch(commit):
                self._increment(excluded, "invalid_validated_commit")
                continue
            if commit in seen:
                self._increment(excluded, "duplicate_validation_record")
                continue
            seen.add(commit)

            block_hash = str(row.get("block_hash") or "").strip().lower()
            validation_run_id = str(row.get("validation_run_id") or "").strip()
            if not HASH_RE.fullmatch(block_hash) or not validation_run_id:
                self._increment(excluded, "incomplete_validation_provenance")
                continue
            if not self._is_ancestor(commit, head_commit):
                self._increment(excluded, "not_promoted_to_current_head")
                continue

            metadata = self._commit_metadata(commit)
            if metadata is None:
                self._increment(excluded, "commit_metadata_unavailable")
                continue
            if (
                (metadata["author_name"], metadata["author_email"]) != GENESIS_AUTHOR
                or (metadata["committer_name"], metadata["committer_email"]) != GENESIS_COMMITTER
            ):
                self._increment(excluded, "not_genesis_autonomous_promotion")
                continue
            if not metadata["message"].startswith(GENESIS_MESSAGE_PREFIX):
                self._increment(excluded, "unexpected_genesis_commit_format")
                continue

            changed_files = self._changed_files(commit)
            recorded_files = row.get("changed_files")
            if not isinstance(recorded_files, list):
                self._increment(excluded, "validation_changed_files_missing")
                continue
            normalized_recorded = tuple(sorted({str(item).strip() for item in recorded_files if str(item).strip()}))
            if normalized_recorded != changed_files:
                self._increment(excluded, "validation_changed_files_mismatch")
                continue
            if not self._safe_code_paths(changed_files):
                self._increment(excluded, "outside_bounded_python_training_scope")
                continue

            patch = self._patch(commit)
            if patch is None:
                self._increment(excluded, "patch_empty_or_over_budget")
                continue

            prompt = (
                "Implement the following independently validated Genesis self-development task.\n"
                f"Objective: {metadata['message']}\n"
                f"Allowed files: {', '.join(changed_files)}\n"
                "Return the minimal code patch that satisfies the objective while preserving existing tests, "
                "security boundaries, independent validation and promotion safeguards."
            )
            examples.append(
                {
                    "prompt": prompt,
                    "response": patch,
                    "provenance": {
                        "classification": "genesis_autonomous_validated_promotion",
                        "policy_version": POLICY_VERSION,
                        "validated_commit": commit,
                        "validation_run_id": validation_run_id,
                        "block_hash": block_hash,
                        "changed_files": list(changed_files),
                        "author_name": metadata["author_name"],
                        "committer_name": metadata["committer_name"],
                    },
                }
            )
            included.append(commit)
            if len(examples) >= max_examples:
                break

        return DatasetCollection(
            examples=tuple(examples),
            included_commits=tuple(included),
            excluded_by_reason=dict(sorted(excluded.items())),
            head_commit=head_commit,
            blockchain_sha256=blockchain_hash,
        )

    def build(
        self,
        *,
        head: str = "HEAD",
        output_name: str | None = None,
        max_examples: int = MAX_EXAMPLES,
    ) -> dict[str, Any]:
        collection = self.collect(head=head, max_examples=max_examples)
        if not collection.examples:
            raise RuntimeError("no provenance-qualified Genesis autonomous training examples are available")

        name = output_name or f"genesis-validated-autonomous-{collection.head_commit[:12]}.jsonl"
        if not OUTPUT_RE.fullmatch(name):
            raise ValueError("output_name must be a simple .jsonl file name")
        self.output_root.mkdir(parents=True, exist_ok=True)
        dataset_path = (self.output_root / name).resolve()
        self._require_inside(dataset_path, self.output_root, "dataset path")
        manifest_path = dataset_path.with_suffix(dataset_path.suffix + ".manifest.json")

        dataset_bytes = b"".join(
            (json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
            for item in collection.examples
        )
        dataset_sha = sha256_bytes(dataset_bytes)
        manifest = {
            "schema_version": 1,
            "policy_version": POLICY_VERSION,
            "dataset_kind": "genesis_validated_autonomous_code_sft",
            "dataset_path": dataset_path.relative_to(self.root).as_posix(),
            "dataset_sha256": dataset_sha,
            "example_count": len(collection.examples),
            "included_commits": list(collection.included_commits),
            "excluded_by_reason": collection.excluded_by_reason,
            "source_head_commit": collection.head_commit,
            "blockchain_path": self.blockchain_path.relative_to(self.root).as_posix(),
            "blockchain_sha256": collection.blockchain_sha256,
            "eligibility_rule": (
                "current-main ancestor + independent validator blockchain record + Genesis AI author + "
                "Genesis Promotion Stager committer + bounded genesis/tests Python patch"
            ),
            "capability_claim": "none; dataset construction is not model training or benchmark evidence",
        }
        manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")

        for path, content in ((dataset_path, dataset_bytes), (manifest_path, manifest_bytes)):
            if path.exists():
                if path.read_bytes() == content:
                    continue
                raise RuntimeError(f"refusing to overwrite a different existing dataset artifact: {path.name}")
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)

        return manifest

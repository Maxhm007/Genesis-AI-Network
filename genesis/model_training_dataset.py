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
PATCH_ID_RE = re.compile(r"^[0-9a-f]{40}$")
OUTPUT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.jsonl$")
GENESIS_AUTHOR = ("Genesis AI", "genesis-ai@users.noreply.github.com")
GENESIS_SOURCE_COMMITTER = GENESIS_AUTHOR
GENESIS_PROMOTION_COMMITTER = ("Genesis Promotion Stager", "genesis-promotion@users.noreply.github.com")
GENESIS_MESSAGE_PREFIX = "Genesis self-development candidate:"
VALIDATION_PRODUCER = "genesis-independent-validator-gate"
VALIDATION_PAYLOAD_TYPE = "validated_update"
MAX_PATCH_BYTES = 256 * 1024
MAX_EXAMPLES = 10_000
POLICY_VERSION = "genesis-validated-autonomous-code-v2"


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

    Candidate validation and promotion use different Git identities and, after a
    rebase, different commit SHAs. A validated source candidate is therefore
    eligible only when either:

    1. that exact Genesis-authored candidate is already an ancestor of the chosen
       main/head; or
    2. it maps uniquely to a current-head Genesis promotion-stager commit with the
       exact same message, changed-file set, and stable Git patch-id.

    This deliberately excludes owner/assistant PRs, unvalidated Genesis branches,
    failed candidates, workflow/config changes and arbitrary repository history.
    The JSONL is a training input only, never evidence that a model was trained or
    that capability improved.
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
        return completed.returncode == 0

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

    @staticmethod
    def _is_genesis_source(metadata: dict[str, str]) -> bool:
        return (
            (metadata["author_name"], metadata["author_email"]) == GENESIS_AUTHOR
            and (metadata["committer_name"], metadata["committer_email"]) == GENESIS_SOURCE_COMMITTER
            and metadata["message"].startswith(GENESIS_MESSAGE_PREFIX)
        )

    @staticmethod
    def _is_genesis_staged_promotion(metadata: dict[str, str]) -> bool:
        return (
            (metadata["author_name"], metadata["author_email"]) == GENESIS_AUTHOR
            and (metadata["committer_name"], metadata["committer_email"]) == GENESIS_PROMOTION_COMMITTER
            and metadata["message"].startswith(GENESIS_MESSAGE_PREFIX)
        )

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

    def _patch_text(self, commit: str) -> str | None:
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
        if not patch or len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
            return None
        return patch

    def _patch_id(self, patch: str) -> str | None:
        completed = subprocess.run(
            ["git", "patch-id", "--stable"],
            cwd=self.root,
            input=patch + "\n",
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        value = completed.stdout.split()[0].strip().lower()
        return value if PATCH_ID_RE.fullmatch(value) else None

    def _promoted_index(
        self,
        head_commit: str,
    ) -> dict[tuple[str, tuple[str, ...], str], tuple[str, ...]]:
        """Index exact autonomous staged promotions reachable from current head."""
        hashes = self._git("rev-list", head_commit).stdout.splitlines()
        bucket: dict[tuple[str, tuple[str, ...], str], list[str]] = {}
        for raw in hashes:
            commit = raw.strip().lower()
            if not COMMIT_RE.fullmatch(commit):
                continue
            metadata = self._commit_metadata(commit)
            if metadata is None or not self._is_genesis_staged_promotion(metadata):
                continue
            changed_files = self._changed_files(commit)
            if not self._safe_code_paths(changed_files):
                continue
            patch = self._patch_text(commit)
            if patch is None:
                continue
            patch_id = self._patch_id(patch)
            if patch_id is None:
                continue
            key = (metadata["message"], changed_files, patch_id)
            bucket.setdefault(key, []).append(commit)
        return {key: tuple(values) for key, values in bucket.items()}

    @staticmethod
    def _increment(bucket: dict[str, int], reason: str) -> None:
        bucket[reason] = bucket.get(reason, 0) + 1

    def collect(self, *, head: str = "HEAD", max_examples: int = MAX_EXAMPLES) -> DatasetCollection:
        if isinstance(max_examples, bool) or not isinstance(max_examples, int) or not 1 <= max_examples <= MAX_EXAMPLES:
            raise ValueError(f"max_examples must be between 1 and {MAX_EXAMPLES}")

        head_commit = self._resolve_head(head)
        rows = self._load_validation_rows()
        blockchain_hash = sha256_file(self.blockchain_path)
        promoted_index = self._promoted_index(head_commit)
        excluded: dict[str, int] = {}
        seen_validations: set[str] = set()
        included_promotions: set[str] = set()
        examples: list[dict[str, Any]] = []
        included: list[str] = []

        for row in rows:
            if row.get("payload_type") != VALIDATION_PAYLOAD_TYPE or row.get("producer") != VALIDATION_PRODUCER:
                self._increment(excluded, "not_independent_validator_record")
                continue

            validated_commit = str(row.get("validated_commit") or "").strip().lower()
            if not COMMIT_RE.fullmatch(validated_commit):
                self._increment(excluded, "invalid_validated_commit")
                continue
            if validated_commit in seen_validations:
                self._increment(excluded, "duplicate_validation_record")
                continue
            seen_validations.add(validated_commit)

            block_hash = str(row.get("block_hash") or "").strip().lower()
            validation_run_id = str(row.get("validation_run_id") or "").strip()
            if not HASH_RE.fullmatch(block_hash) or not validation_run_id:
                self._increment(excluded, "incomplete_validation_provenance")
                continue

            source_metadata = self._commit_metadata(validated_commit)
            if source_metadata is None:
                self._increment(excluded, "commit_metadata_unavailable")
                continue
            source_is_genesis = self._is_genesis_source(source_metadata)
            source_is_staged = self._is_genesis_staged_promotion(source_metadata)
            if not source_is_genesis and not source_is_staged:
                self._increment(excluded, "not_genesis_autonomous_candidate")
                continue

            source_files = self._changed_files(validated_commit)
            recorded_files = row.get("changed_files")
            if not isinstance(recorded_files, list):
                self._increment(excluded, "validation_changed_files_missing")
                continue
            normalized_recorded = tuple(sorted({str(item).strip() for item in recorded_files if str(item).strip()}))
            if normalized_recorded != source_files:
                self._increment(excluded, "validation_changed_files_mismatch")
                continue
            if not self._safe_code_paths(source_files):
                self._increment(excluded, "outside_bounded_python_training_scope")
                continue

            source_patch = self._patch_text(validated_commit)
            if source_patch is None:
                self._increment(excluded, "patch_empty_or_over_budget")
                continue
            source_patch_id = self._patch_id(source_patch)
            if source_patch_id is None:
                self._increment(excluded, "patch_identity_unavailable")
                continue

            promoted_commit: str | None = None
            promotion_mapping = ""
            if self._is_ancestor(validated_commit, head_commit):
                # A fast-forward promotion can leave the original Genesis AI
                # candidate SHA unchanged; an already staged SHA may also have
                # been independently validated directly.
                promoted_commit = validated_commit
                promotion_mapping = "validated_commit_is_current_head_ancestor"
            else:
                key = (source_metadata["message"], source_files, source_patch_id)
                matches = promoted_index.get(key, ())
                if len(matches) == 1:
                    promoted_commit = matches[0]
                    promotion_mapping = "stable_patch_id+message+files+promotion_identity"
                elif len(matches) > 1:
                    self._increment(excluded, "ambiguous_promoted_patch_mapping")
                    continue
                else:
                    self._increment(excluded, "validated_candidate_not_promoted_to_current_head")
                    continue

            if promoted_commit in included_promotions:
                self._increment(excluded, "duplicate_promoted_training_example")
                continue
            promoted_metadata = self._commit_metadata(promoted_commit)
            if promoted_metadata is None:
                self._increment(excluded, "promoted_commit_metadata_unavailable")
                continue
            # For a rebased/staged mapping, promotion identity is mandatory. For
            # an unchanged fast-forward candidate, exact Genesis source identity
            # plus independent validation and current-head ancestry is sufficient.
            if promoted_commit != validated_commit and not self._is_genesis_staged_promotion(promoted_metadata):
                self._increment(excluded, "mapped_commit_missing_promotion_identity")
                continue
            promoted_files = self._changed_files(promoted_commit)
            promoted_patch = self._patch_text(promoted_commit)
            if promoted_files != source_files or promoted_patch is None:
                self._increment(excluded, "promoted_patch_scope_mismatch")
                continue
            promoted_patch_id = self._patch_id(promoted_patch)
            if promoted_patch_id != source_patch_id:
                self._increment(excluded, "promoted_patch_identity_mismatch")
                continue
            if promoted_metadata["message"] != source_metadata["message"]:
                self._increment(excluded, "promoted_message_mismatch")
                continue

            prompt = (
                "Implement the following independently validated Genesis self-development task.\n"
                f"Objective: {source_metadata['message']}\n"
                f"Allowed files: {', '.join(source_files)}\n"
                "Return the minimal code patch that satisfies the objective while preserving existing tests, "
                "security boundaries, independent validation and promotion safeguards."
            )
            examples.append(
                {
                    "prompt": prompt,
                    "response": promoted_patch,
                    "provenance": {
                        "classification": "genesis_autonomous_validated_promotion",
                        "policy_version": POLICY_VERSION,
                        "validated_source_commit": validated_commit,
                        "promoted_commit": promoted_commit,
                        "validation_run_id": validation_run_id,
                        "block_hash": block_hash,
                        "changed_files": list(source_files),
                        "stable_patch_id": source_patch_id,
                        "promotion_mapping": promotion_mapping,
                        "source_author_name": source_metadata["author_name"],
                        "source_committer_name": source_metadata["committer_name"],
                        "promoted_author_name": promoted_metadata["author_name"],
                        "promoted_committer_name": promoted_metadata["committer_name"],
                    },
                }
            )
            included_promotions.add(promoted_commit)
            included.append(promoted_commit)
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
            "schema_version": 2,
            "policy_version": POLICY_VERSION,
            "dataset_kind": "genesis_validated_autonomous_code_sft",
            "dataset_path": dataset_path.relative_to(self.root).as_posix(),
            "dataset_sha256": dataset_sha,
            "example_count": len(collection.examples),
            "included_promoted_commits": list(collection.included_commits),
            "excluded_by_reason": collection.excluded_by_reason,
            "source_head_commit": collection.head_commit,
            "blockchain_path": self.blockchain_path.relative_to(self.root).as_posix(),
            "blockchain_sha256": collection.blockchain_sha256,
            "eligibility_rule": (
                "independently validated Genesis AI candidate + current-head ancestry OR unique stable-patch-id/message/files "
                "mapping to Genesis Promotion Stager commit + bounded genesis/tests Python patch"
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

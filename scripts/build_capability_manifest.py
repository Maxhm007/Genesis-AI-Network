#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "GENE_CAPABILITY_EXPORT.json"
OUTPUT = ROOT / "GENE_CAPABILITY_MANIFEST.json"


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe {label}: {value}")
    return path


def source_commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("unsupported export schema_version")

    protected = list(config.get("protected_descendant_paths", []))
    exports: list[dict] = []

    for item in config.get("exports", []):
        source = safe_relative(str(item["source"]), "source")
        target = safe_relative(str(item["target"]), "target")
        if not str(target).startswith("inherited/gene0/"):
            raise ValueError(f"export target must be under inherited/gene0/: {target}")

        src_path = ROOT.joinpath(*source.parts)
        if not src_path.is_file():
            raise FileNotFoundError(src_path)
        data = src_path.read_bytes()

        exports.append(
            {
                "id": str(item["id"]),
                "source": str(source),
                "target": str(target),
                "kind": str(item.get("kind", "file")),
                "size": len(data),
                "sha256": sha256_bytes(data),
            }
        )

    release_material = {
        "schema_version": 1,
        "release_version": config["release_version"],
        "publisher": config["publisher"],
        "compatibility": config["compatibility"],
        "protected_descendant_paths": protected,
        "exports": exports,
    }
    release_id = sha256_bytes(canonical_bytes(release_material))

    manifest = {
        **release_material,
        "release_id": release_id,
        "source_commit": source_commit(),
        "activation_rule": "download -> verify sha256 -> stage -> validate -> commit",
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Published Gene 0 capability release {config['release_version']} {release_id[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

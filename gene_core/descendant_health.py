#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_LOCAL_JSON = ("node.json", "GENE_REGISTRY.json", "LEARNING_POLICY.json")
STATE_PATH = "GENE0_INHERITANCE_STATE.json"
CATALOG_PATH = "inherited/gene0/core/CAPABILITIES.json"
EXPECTED_PUBLISHER = "Maxhm007/Genesis-AI-Network"


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def validate(repo: Path) -> list[str]:
    errors: list[str] = []
    loaded: dict[str, dict] = {}

    for relative in REQUIRED_LOCAL_JSON:
        path = repo / relative
        if not path.is_file():
            errors.append(f"missing local state: {relative}")
            continue
        try:
            loaded[relative] = load_json(path)
        except Exception as exc:  # noqa: BLE001 - validator reports all failures
            errors.append(f"invalid JSON {relative}: {exc}")

    state_file = repo / STATE_PATH
    if not state_file.is_file():
        errors.append(f"missing inheritance state: {STATE_PATH}")
        return errors

    try:
        state = load_json(state_file)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid JSON {STATE_PATH}: {exc}")
        return errors

    node = loaded.get("node.json", {})
    if state.get("node_id") != node.get("node_id"):
        errors.append("inheritance state node_id does not match node.json")
    if state.get("publisher_repository") != EXPECTED_PUBLISHER:
        errors.append("inheritance state publisher is not Gene 0")
    if not state.get("release_id"):
        errors.append("inheritance state has no release_id")
    if not state.get("release_version"):
        errors.append("inheritance state has no release_version")

    catalog_file = repo / CATALOG_PATH
    if not catalog_file.is_file():
        errors.append(f"missing inherited capability catalog: {CATALOG_PATH}")
    else:
        try:
            catalog = load_json(catalog_file)
            if not isinstance(catalog.get("capabilities"), list):
                errors.append("inherited capability catalog has no capabilities list")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid inherited capability catalog: {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Genesis descendant after Gene 0 inheritance")
    parser.add_argument("--repo", default=".", help="descendant repository root")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    errors = validate(repo)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Gene 0 inherited core and descendant-local state are healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

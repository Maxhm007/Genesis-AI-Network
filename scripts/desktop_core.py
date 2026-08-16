from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from genesis.communication_server import serve


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])).resolve()


def persistent_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "GenesisAI"


def ensure_workspace() -> Path:
    source = bundled_root()
    target = persistent_root()
    target.mkdir(parents=True, exist_ok=True)
    for relative in ("GENESIS_CONSTITUTION.md", "GENESIS_BLOCK.json"):
        src = source / relative
        dst = target / relative
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    for relative in ("config", "web", "genesis"):
        src = source / relative
        dst = target / relative
        if src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)
    (target / "runtime").mkdir(exist_ok=True)
    return target


def main() -> None:
    root = ensure_workspace()
    serve(root, "127.0.0.1", 8787, "")


if __name__ == "__main__":
    main()

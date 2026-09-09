from __future__ import annotations

from pathlib import Path

# Direct execution such as `python scripts/requeue_exhausted_issues.py`
# places `scripts/` first on sys.path. Extend this shim package to the real
# repository-level `genesis/` package so imports like
# `genesis.github_issue_detected_reconciler` resolve consistently in Actions.
_real_package = Path(__file__).resolve().parents[2] / "genesis"
if _real_package.is_dir():
    __path__.append(str(_real_package))

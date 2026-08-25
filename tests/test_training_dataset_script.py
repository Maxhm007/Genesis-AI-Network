from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_training_dataset_script_imports_genesis_without_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "scripts/build_genesis_training_dataset.py", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Build a provenance-qualified SFT dataset" in result.stdout

"""End-to-end disposable fixture test for the other repository's repair engine.

This is an acceptance test of peer-authored code generation, patch guards and
actual failing/passing unittest behavior. It does not modify production code.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

def cmd(*args, cwd):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=35,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

def main():
    peer_file = Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("vetted_peer_repair", peer_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = "def answer():\n    return 1\n"
    meta = {
        "source": {"path": "src/demo.py", "content": original},
        "failures": [{"log_excerpt": "AssertionError: 1 != 2"}],
    }
    patch = module.deterministic_patch(meta)
    if not patch or module.inspect_patch(patch) != "src/demo.py":
        raise AssertionError("Peer engine did not create a permitted one-file repair")
    with tempfile.TemporaryDirectory(prefix="peer-code-repair-") as td:
        work = Path(td)
        (work / "src").mkdir()
        (work / "tests").mkdir()
        (work / "src" / "__init__.py").write_text("")
        source = work / "src" / "demo.py"
        source.write_text(original)
        (work / "tests" / "test_demo.py").write_text(
            "import unittest\nfrom src.demo import answer\n"
            "class TestRepair(unittest.TestCase):\n"
            "    def test_expected_value(self):\n"
            "        self.assertEqual(answer(), 2)\n"
        )
        baseline = cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", cwd=work)
        if baseline.returncode == 0 or "FAIL" not in baseline.stderr:
            raise AssertionError("Baseline fixture was not genuinely failing")
        patch_path = work / "candidate.patch"
        patch_path.write_text(patch)
        check = cmd("git", "apply", "--check", str(patch_path), cwd=work)
        if check.returncode:
            raise AssertionError("Peer patch does not apply: " + check.stderr)
        applied = cmd("git", "apply", str(patch_path), cwd=work)
        if applied.returncode:
            raise AssertionError("Peer patch application failed: " + applied.stderr)
        module.enforce_literal_return_repair(original.encode(), source.read_bytes())
        verified = cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", cwd=work)
        if verified.returncode or "OK" not in verified.stderr:
            raise AssertionError("Patched fixture tests did not pass: " + verified.stderr)
        if source.read_text() != "def answer():\n    return 2\n":
            raise AssertionError("Patch was not the expected bounded literal change")
    print(json.dumps({"status": "peer_code_repair_fixture_passed",
                      "peer_engine": str(peer_file),
                      "baseline": "failed", "patched": "passed",
                      "changed_file": "src/demo.py", "mode": "disposable_fixture"}))

if __name__ == "__main__":
    main()

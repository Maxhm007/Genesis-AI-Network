"""Pure-policy tests for mutual code repair, no GitHub or model network calls."""
import base64
import hashlib
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def module():
    root = Path(__file__).resolve().parents[1]
    path = root / "repair_v2.py"
    if not path.exists():
        path = root / "scripts" / "repair_v2.py"
    spec = importlib.util.spec_from_file_location("repair_policy", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


repair = module()


class RepairTests(unittest.TestCase):
    def test_directionality(self):
        self.assertEqual(repair.peer("genesis"), "eve")
        self.assertEqual(repair.peer("eve"), "genesis")
        with self.assertRaises(ValueError):
            repair.peer("unknown")

    def test_python_patch_whitelist(self):
        patch = ("diff --git a/eve/core.py b/eve/core.py\n"
                 "--- a/eve/core.py\n+++ b/eve/core.py\n"
                 "@@ -1 +1 @@\n-a=1\n+a=2\n")
        self.assertEqual(repair.inspect_patch(patch), "eve/core.py")

    def test_privileged_files_rejected(self):
        for path in ("../a.py", ".github/workflows/repair.py", "setup.py",
                     "tests/conftest.py", "eve/../../x.py", "file.yml",
                     "sitecustomize.py", "/tmp/a.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                repair.valid_path(path)

    def test_multi_file_patch_rejected(self):
        patch = ("diff --git a/eve/a.py b/eve/a.py\n"
                 "--- a/eve/a.py\n+++ b/eve/a.py\n@@ -1 +1 @@\n-a\n+b\n"
                 "diff --git a/eve/b.py b/eve/b.py\n"
                 "--- a/eve/b.py\n+++ b/eve/b.py\n@@ -1 +1 @@\n-a\n+b\n")
        with self.assertRaises(ValueError):
            repair.inspect_patch(patch)

    def test_only_repeated_recent_failures_on_main(self):
        now = datetime.now(timezone.utc)
        run = {
            "status":"completed", "conclusion":"failure", "run_attempt":2,
            "head_branch":"main", "head_sha":"a"*40,
            "created_at": (now-timedelta(hours=1)).isoformat()
        }
        self.assertTrue(repair.eligible_run(run))
        self.assertFalse(repair.eligible_run({**run,"run_attempt":1}))
        self.assertFalse(repair.eligible_run({**run,"head_branch":"pull/2"}))
        self.assertFalse(repair.eligible_run({**run,"head_sha":"bad"}))
        self.assertFalse(repair.eligible_run({**run,"created_at":(now-timedelta(days=3)).isoformat()}))

    def test_no_pr_without_attestation(self):
        meta={"healer":"genesis","target":"eve","repo":repair.REPOS["eve"],
              "path":"eve/core.py","new_sha256":hashlib.sha256(b"fix").hexdigest(),
              "baseline":"passed","patched":"passed",
              "test_command":"python -m unittest discover -s tests -v"}
        with self.assertRaises(ValueError):
            repair.publish(meta,base64.b64encode(b"fix").decode(),"secret")

    def test_no_pr_wrong_agent(self):
        meta={"healer":"genesis","target":"genesis","repo":repair.REPOS["genesis"],
              "path":"eve/core.py","new_sha256":hashlib.sha256(b"fix").hexdigest(),
              "baseline":"failed","patched":"passed",
              "test_command":"python -m unittest discover -s tests -v"}
        with self.assertRaises(ValueError):
            repair.publish(meta,base64.b64encode(b"fix").decode(),"secret")

    def test_declines_insecure_model_url(self):
        meta={"healer":"genesis","failures":[],"run_url":"x","sha":"a"*40}
        with self.assertRaises(ValueError):
            repair.model_patch(meta,"http://example.com/v1/chat/completions","model","")


if __name__=="__main__":
    unittest.main()

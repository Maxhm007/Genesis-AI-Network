"""Pure-policy tests for mutual code repair, no GitHub or model network calls."""
import base64
import hashlib
import importlib.util
import subprocess
import tempfile
from unittest import mock
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

    def test_root_level_source_is_found_from_realistic_traceback(self):
        # The recipient repository has root modules; its traceback may not
        # contain the previously required eve/ or src/ directory prefix.
        import base64
        repo = repair.REPOS["eve"]
        sha = "a" * 40
        log = 'File "/home/runner/work/Eve/Eve/mutual_healer.py", line 41, in heal_once'
        response = {
            "type": "file", "encoding": "base64",
            "content": base64.b64encode(b"def marker():\\n    return 1\\n").decode(),
        }
        with mock.patch.object(repair, "_api", return_value=response) as read:
            result = repair.source_from_traceback(repo, sha, log, "local-token")
        self.assertEqual(result["path"], "mutual_healer.py")
        self.assertIn("return 1", result["content"])
        self.assertIn("/contents/mutual_healer.py?ref=" + sha, read.call_args.args[1])

    def test_arbitrary_root_module_is_not_trusted_without_known_prefix(self):
        repo = repair.REPOS["eve"]
        log = 'File "/tmp/unknown_library.py", line 2, in run'
        with mock.patch.object(repair, "_api") as read:
            self.assertIsNone(repair.source_from_traceback(repo, "a"*40, log))
        read.assert_not_called()


    def test_pytest_only_candidate_attests_correct_runner(self):
        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest unavailable")
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n")
        def checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "src" / "__init__.py").write_text("")
            (dest / "tests").mkdir()
            (dest / "requirements.txt").write_text("pytest>=8.0\n")
            (dest / "src" / "calc.py").write_text("def value():\n    return 1\n")
            (dest / "tests" / "test_calc.py").write_text(
                "from src.calc import value\n"
                "def test_value(): assert value() == 2\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer": "eve", "target": "genesis",
                "repo": repair.REPOS["genesis"], "sha": "a"*40,
                "run_id": 123, "run_url": "https://github.com/test"}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", checkout):
            attestation = repair.validate(meta, patch, Path(d)/"verified")
            self.assertEqual(attestation["test_command"], "python -m pytest -q tests")
            self.assertEqual(attestation["baseline"], "failed")
            self.assertEqual(attestation["patched"], "passed")
            self.assertEqual(attestation["tests_executed"], 1)

    def test_real_pytest_collection_error_is_reproducible(self):
        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest unavailable")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            (root / "src" / "__init__.py").write_text("")
            (root / "tests").mkdir()
            (root / "requirements.txt").write_text("pytest>=8.0\n")
            source = root / "src" / "calc.py"
            source.write_text("def value():\n    return 1\n")
            (root / "tests" / "test_collection.py").write_text(
                "from src.calc import value\n"
                "assert value() == 2\n"
                "def test_runtime(): assert value() == 2\n")
            broken, baseline = repair.run_tracked_tests(root)
            self.assertNotEqual(broken.returncode, 0)
            self.assertGreaterEqual(baseline["errors"], 1)
            self.assertEqual(baseline["executed"], 0)
            source.write_text("def value():\n    return 2\n")
            fixed, patched = repair.run_tracked_tests(root)
            self.assertEqual(fixed.returncode, 0)
            self.assertEqual(patched["executed"], 1)
            self.assertTrue(patched["successful"])

    def test_real_pytest_assertion_is_reproduced_and_fixed(self):
        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest unavailable in policy test environment")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tests").mkdir()
            (root / "requirements.txt").write_text("pytest>=8.0\n")
            candidate = root / "tests" / "test_actual_pytest.py"
            candidate.write_text("def test_actual_value():\n    assert 1 == 2\n")
            original, baseline = repair.run_tracked_tests(root)
            self.assertNotEqual(original.returncode, 0)
            self.assertEqual(baseline["discovered"], 1)
            self.assertEqual(baseline["executed"], 1)
            self.assertEqual(baseline["failures"], 1)
            candidate.write_text("def test_actual_value():\n    assert 2 == 2\n")
            repaired, stats = repair.run_tracked_tests(root)
            self.assertEqual(repaired.returncode, 0)
            self.assertEqual(stats["discovered"], 1)
            self.assertEqual(stats["executed"], 1)
            self.assertTrue(stats["successful"])

    def test_empty_pytest_suite_does_not_forge_reproduction(self):
        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest unavailable")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "tests").mkdir()
            (root / "requirements.txt").write_text("pytest>=8.0\n")
            (root / "tests" / "test_skip_all.py").write_text(
                "import pytest\npytest.skip('no tests', allow_module_level=True)\n")
            with self.assertRaisesRegex(ValueError, "incomplete or invalid"):
                repair.run_tracked_tests(root)

    def test_patch_cannot_replace_collection_failure_with_module_skip(self):
        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest unavailable")
        patch = ("diff --git a/src/flag.py b/src/flag.py\n"
                 "--- a/src/flag.py\n+++ b/src/flag.py\n"
                 "@@ -1,2 +1,2 @@\n def enabled():\n-    return True\n+    return False\n")
        def checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "src" / "__init__.py").write_text("")
            (dest / "tests").mkdir()
            (dest / "requirements.txt").write_text("pytest>=8.0\n")
            (dest / "src" / "flag.py").write_text("def enabled():\n    return True\n")
            (dest / "tests" / "test_skip.py").write_text(
                "import pytest\nfrom src.flag import enabled\n"
                "if not enabled(): pytest.skip('feature disabled', allow_module_level=True)\n"
                "assert enabled() is False\n"
                "def test_flag(): assert True\n")
            (dest / "tests" / "test_other.py").write_text(
                "def test_other(): assert True\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer": "eve", "target": "genesis",
                "repo": repair.REPOS["genesis"], "sha": "a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", checkout):
            with self.assertRaisesRegex(ValueError, "skipped additional test modules"):
                repair.validate(meta, patch, Path(d)/"verified")

    def test_genesis_pytest_collection_is_tracked(self):
        import types
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "requirements.txt").write_text("cryptography>=42.0\npytest>=8.0\n")
            done = "__MUTUAL_HEAL_SUITE_FINISHED__" + "a"*32 + ":"
            report = '{"discovered":3,"executed":3,"failures":0,"errors":0,"skipped":0,"successful":true}'
            result = types.SimpleNamespace(returncode=0, stdout=done+report+"\n", stderr="")
            with mock.patch.object(repair.secrets, "token_hex", return_value="a"*32), \
                 mock.patch.object(repair, "command", return_value=result) as command:
                _, stats = repair.run_tracked_tests(root)
                self.assertTrue(stats["successful"])
                args = command.call_args.args[0]
                self.assertIn("pytest.main", args[2])
                self.assertIn("pytest_runtest_logreport", args[2])

    def test_unittest_repo_keeps_unittest_completion_harness(self):
        import types
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            done = "__MUTUAL_HEAL_SUITE_FINISHED__" + "b"*32 + ":"
            report = '{"discovered":1,"executed":1,"failures":0,"errors":0,"skipped":0,"successful":true}'
            result = types.SimpleNamespace(returncode=0, stdout=done+report+"\n", stderr="")
            with mock.patch.object(repair.secrets, "token_hex", return_value="b"*32), \
                 mock.patch.object(repair, "command", return_value=result) as command:
                repair.run_tracked_tests(root)
                args = command.call_args.args[0]
                self.assertIn("unittest.defaultTestLoader", args[2])
                self.assertNotIn("pytest.main", args[2])

    def test_publisher_rejects_unattested_test_runner(self):
        meta = {
            "healer": "genesis", "target": "eve", "repo": repair.REPOS["eve"],
            "path": "src/calc.py", "new_sha256": hashlib.sha256(b"ok").hexdigest(),
            "baseline": "failed", "patched": "passed", "tests_completed": True,
            "tests_executed": 2, "test_command": "python -c 'print(1)'"
        }
        with self.assertRaisesRegex(ValueError, "reproduction evidence"):
            repair.publish(meta, base64.b64encode(b"ok").decode(), "fake-local-token")

    def test_local_prepare_requires_matching_recipient_repository(self):
        import os
        import sys
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": repair.REPOS["genesis"],
                                          "GITHUB_TOKEN": "local-scoped-token"}, clear=True), \
             mock.patch.object(sys, "argv", ["repair_v2.py", "--local", "prepare",
                                             "--identity", "genesis", "--out", "candidate"]), \
             mock.patch.object(repair, "evidence") as evidence:
            with self.assertRaisesRegex(ValueError, "current repository"):
                repair.main()
            evidence.assert_not_called()

    def test_local_prepare_uses_native_token_on_local_target_only(self):
        import os
        import sys
        import io
        from contextlib import redirect_stdout
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": repair.REPOS["eve"],
                                          "GITHUB_TOKEN": "local-scoped-token"}, clear=True), \
             mock.patch.object(sys, "argv", ["repair_v2.py", "--local", "prepare",
                                             "--identity", "genesis", "--out", "candidate"]), \
             mock.patch.object(repair, "evidence", return_value=None) as evidence, \
             redirect_stdout(io.StringIO()):
            repair.main()
            evidence.assert_called_once_with("genesis", 0, "local-scoped-token")

    def test_local_publisher_rejects_foreign_repository_without_writing(self):
        import os
        import sys
        import json
        with tempfile.TemporaryDirectory() as d:
            verified = Path(d)
            (verified / "attestation.json").write_text(json.dumps({
                "healer": "eve", "target": "genesis"}))
            (verified / "patched.b64").write_text("ZGF0YQ==")
            with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": repair.REPOS["eve"],
                                              "GITHUB_TOKEN": "local-scoped-token"}, clear=True), \
                 mock.patch.object(sys, "argv", ["repair_v2.py", "--local", "publish",
                                                 "--verified", str(verified)]), \
                 mock.patch.object(repair, "publish") as publisher:
                with self.assertRaisesRegex(ValueError, "foreign repository"):
                    repair.main()
                publisher.assert_not_called()

    def test_local_publisher_uses_local_token_instead_of_peer_pat(self):
        import os
        import sys
        import json
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            verified = Path(d)
            meta = {"healer": "genesis", "target": "eve", "repo": repair.REPOS["eve"]}
            (verified / "attestation.json").write_text(json.dumps(meta))
            (verified / "patched.b64").write_text("ZGF0YQ==")
            with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": repair.REPOS["eve"],
                                              "GITHUB_TOKEN": "local-scoped-token",
                                              "REPAIR_PR_TOKEN": "must-not-use"}, clear=True), \
                 mock.patch.object(sys, "argv", ["repair_v2.py", "--local", "publish",
                                                 "--verified", str(verified)]), \
                 mock.patch.object(repair, "publish", return_value={"status": "review_required"}) as publisher, \
                 redirect_stdout(io.StringIO()):
                repair.main()
                publisher.assert_called_once_with(meta, "ZGF0YQ==", "local-scoped-token")



    def test_deterministic_patch_without_final_newline_applies_with_git(self):
        import subprocess
        meta = {"source": {"path": "src/calc.py",
                           "content": "def value():\n    return 1"},
                "failures": [{"log_excerpt": "E       assert 1 == 2"}]}
        diff = repair.deterministic_patch(meta)
        self.assertIn("\\ No newline at end of file", diff)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            (root / "src" / "calc.py").write_bytes(meta["source"]["content"].encode())
            patch = root / "repair.patch"
            patch.write_text(diff)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=root, check=True)
            subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
            self.assertEqual((root / "src" / "calc.py").read_bytes(),
                             b"def value():\n    return 2")

    def test_deterministic_candidate_without_ai_provider(self):
        source = {"path": "src/calc.py", "content": "def value():\n    return 1\n"}
        meta = {"source": source, "failures": [
            {"log_excerpt": "E       assert 1 == 2\n"}]}
        patch = repair.deterministic_patch(meta)
        self.assertIsInstance(patch, str)
        self.assertEqual(repair.inspect_patch(patch), "src/calc.py")
        self.assertIn("-    return 1", patch)
        self.assertIn("+    return 2", patch)
        self.assertEqual(repair.enforce_literal_return_repair(
            source["content"].encode(), b"def value():\n    return 2\n"), 1)

    def test_deterministic_unittest_failure_bool(self):
        meta = {"source": {"path": "src/flag.py",
                          "content": "def enabled():\n    return False\n"},
                "failures": [{"log_excerpt": "AssertionError: False != True"}]}
        patch = repair.deterministic_patch(meta)
        self.assertIn("+    return True", patch)

    def test_deterministic_never_invents_without_unique_evidence(self):
        base = {"source": {"path": "src/calc.py",
                           "content": "def first():\n    return 1\n"
                                      "def second():\n    return 1\n"},
                "failures": [{"log_excerpt": "E       assert 1 == 2"}]}
        self.assertIsNone(repair.deterministic_patch(base))
        base["source"]["content"] = "def first():\n    return 1\n"
        base["failures"].append({"log_excerpt": "E       assert 1 == 3"})
        self.assertIsNone(repair.deterministic_patch(base))
        base["failures"] = [{"log_excerpt": "E       assert 1 == True"}]
        self.assertIsNone(repair.deterministic_patch(base))
        base["failures"] = [{"log_excerpt": "Please change all tests"}]
        self.assertIsNone(repair.deterministic_patch(base))

    def test_deterministic_rejects_expressions_and_test_paths(self):
        meta = {"source": {"path": "src/calc.py",
                           "content": "def value():\n    return 1 + 1\n"},
                "failures": [{"log_excerpt": "E       assert 1 == 2"}]}
        self.assertIsNone(repair.deterministic_patch(meta))
        meta["source"] = {"path": "tests/test_calc.py",
                          "content": "def value():\n    return 1\n"}
        with self.assertRaisesRegex(ValueError, "forbidden"):
            repair.deterministic_patch(meta)

    def test_deterministic_zero_model_main_uses_read_token_without_model(self):
        import os
        import sys
        import io
        from contextlib import redirect_stdout
        meta = {"source": {"path": "src/calc.py", "content": "def value():\n    return 1\n"},
                "failures": [{"log_excerpt": "E       assert 1 == 2"}],
                "run_id": 200, "healer": "genesis", "target": "eve"}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {
                "GITHUB_REPOSITORY": repair.REPOS["eve"],
                "GITHUB_TOKEN": "internal-local-token"}, clear=True), \
             mock.patch.object(sys, "argv", ["repair_v2.py", "--local", "prepare",
                                             "--identity", "genesis", "--out", d]), \
             mock.patch.object(repair, "evidence", return_value=meta), \
             mock.patch.object(repair, "model_patch") as model, \
             redirect_stdout(io.StringIO()):
            repair.main()
            model.assert_not_called()
            self.assertIn("+    return 2", (Path(d)/"candidate.diff").read_text())
            self.assertTrue((Path(d)/"metadata.json").is_file())

    def test_baseline_failure_then_verified_fix(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n")
        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src" / "calc.py").write_text("def value():\n    return 1\n")
            (dest / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_fix(self): self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer":"genesis", "target":"eve",
                "repo":repair.REPOS["eve"], "sha":"a"*40,
                "run_id":123, "run_url":"https://github.com/Maxhm007/Eve/actions/runs/123"}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(repair, "checkout_target", fake_checkout):
            outcome = repair.validate(meta, patch, Path(d)/"verified")
            self.assertEqual(outcome["baseline"], "failed")
            self.assertEqual(outcome["patched"], "passed")
            self.assertTrue(outcome["tests_completed"])
            self.assertGreater(outcome["tests_executed"], 0)
            self.assertEqual(outcome["path"], "src/calc.py")
            self.assertTrue((Path(d)/"verified"/"attestation.json").is_file())
            self.assertTrue((Path(d)/"verified"/"patched.b64").is_file())

    def test_model_preserves_final_diff_newline(self):
        import json
        diff = ("diff --git a/src/calc.py b/src/calc.py\n"
                "--- a/src/calc.py\n+++ b/src/calc.py\n"
                "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2")
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, count): return json.dumps({
                "choices": [{"message": {"content": diff}}]}).encode()
        meta = {"healer": "genesis", "failures": [],
                "source": {"path":"src/calc.py", "content":"def value(): pass"},
                "run_url":"test", "sha":"a"*40}
        with mock.patch.object(repair.urllib.request, "urlopen", lambda *a, **k: Response()):
            result = repair.model_patch(meta, "https://example.org/v1/chat/completions", "model", "")
        self.assertTrue(result.endswith("\n"))
        self.assertEqual(repair.inspect_patch(result), "src/calc.py")

    def test_source_context_reaches_model(self):
        import io
        import json
        context = {"healer": "eve", "failures": [{"job": "tests", "log_excerpt": "NameError"}],
                   "source": {"path": "scripts/helper.py", "content": "def fix(): return 1"},
                   "run_url": "https://github.com/Maxhm007/Genesis-AI-Network/actions/runs/10",
                   "sha": "a"*40}
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, count): return b'{"choices":[{"message":{"content":"NO_SAFE_PATCH"}}]}'
        def fake_open(request, timeout):
            captured.update(json.loads(request.data))
            return Response()
        with mock.patch.object(repair.urllib.request, "urlopen", fake_open):
            self.assertIsNone(repair.model_patch(
                context, "https://example.org/v1/chat/completions", "test", ""))
        msg = captured["messages"][1]["content"]
        self.assertIn("scripts/helper.py", msg)
        self.assertIn("def fix(): return 1", msg)

    def test_rejects_patch_that_rewrites_source_during_tests(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,3 @@\n def value():\n-    return 1\n"
                 '+    open(__file__, "w").write("def value(): pass")\n'
                 "+    return 2\n")
        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src" / "calc.py").write_text("def value():\n    return 1\n")
            (dest / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_fix(self): self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer":"genesis", "target":"eve", "repo":repair.REPOS["eve"], "sha":"a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(repair, "checkout_target", fake_checkout):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.validate(meta, patch, Path(d)/"verified")

    def test_exit_zero_before_tests_complete_is_rejected(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,4 @@\n"
                 "+import os\n+os._exit(0)\n"
                 " def value():\n     return 1\n")

        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src" / "calc.py").write_text("def value():\n    return 1\n")
            (dest / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_fix(self): self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)

        meta = {"healer": "genesis", "target": "eve",
                "repo": repair.REPOS["eve"], "sha": "a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", fake_checkout):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.validate(meta, patch, Path(d)/"verified")
            self.assertFalse((Path(d)/"verified"/"attestation.json").exists())

    def test_publisher_refuses_missing_test_completion_attestation(self):
        meta = {"healer": "genesis", "target": "eve",
                "repo": repair.REPOS["eve"], "path": "src/calc.py",
                "new_sha256": hashlib.sha256(b"safe").hexdigest(),
                "baseline": "failed", "patched": "passed",
                "test_command": "python -m unittest discover -s tests -v"}
        with self.assertRaisesRegex(ValueError, "reproduction evidence"):
            repair.publish(meta, base64.b64encode(b"safe").decode(), "secret")

    def test_repairing_import_error_can_restore_additional_tests(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1 @@\n"
                 '-raise RuntimeError("broken import")\n'
                 " def value(): return 2\n")

        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src" / "calc.py").write_text(
                'raise RuntimeError("broken import")\ndef value(): return 2\n')
            (dest / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_first(self): self.assertEqual(value(), 2)\n"
                "    def test_second(self): self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)

        meta = {"healer": "genesis", "target": "eve",
                "repo": repair.REPOS["eve"], "sha": "a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", fake_checkout):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.validate(meta, patch, Path(d)/"verified")

    def test_no_newline_stdout_cannot_hide_completion_marker(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return 2\n")
        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src"/"calc.py").write_text("def value():\n    return 1\n")
            (dest / "tests"/"test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_fix(self):\n"
                "        print('progress', end='')\n"
                "        self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer":"genesis","target":"eve","repo":repair.REPOS["eve"],"sha":"a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", fake_checkout):
            result = repair.validate(meta, patch, Path(d)/"verified")
            self.assertTrue(result["tests_completed"])
            self.assertEqual(result["tests_executed"], 1)

    def test_baseline_setup_class_failure_is_valid_reproduction(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1,2 @@\n def boot():\n"
                 "-    raise RuntimeError('broken')\n"
                 "+    return 2\n")
        def fake_checkout(meta, dest):
            (dest / "src").mkdir(parents=True)
            (dest / "tests").mkdir()
            (dest / "src"/"calc.py").write_text(
                "def boot():\n    raise RuntimeError('broken')\n")
            (dest / "tests"/"test_calc.py").write_text(
                "import unittest\nfrom src.calc import boot\n"
                "class TestCalc(unittest.TestCase):\n"
                "    @classmethod\n    def setUpClass(cls): boot()\n"
                "    def test_first(self): self.assertTrue(True)\n"
                "    def test_second(self): self.assertTrue(True)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer":"genesis","target":"eve","repo":repair.REPOS["eve"],"sha":"a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", fake_checkout):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.validate(meta, patch, Path(d)/"verified")

    def test_restored_import_can_reveal_preexisting_skipped_tests(self):
        patch = ("diff --git a/src/calc.py b/src/calc.py\n"
                 "--- a/src/calc.py\n+++ b/src/calc.py\n"
                 "@@ -1,2 +1 @@\n"
                 '-raise RuntimeError("broken import")\n'
                 " def value(): return 2\n")

        def fake_checkout(meta, dest):
            (dest/"src").mkdir(parents=True)
            (dest/"tests").mkdir()
            (dest/"src"/"calc.py").write_text(
                'raise RuntimeError("broken import")\ndef value(): return 2\n')
            (dest/"tests"/"test_calc.py").write_text(
                "import unittest\nfrom src.calc import value\n"
                "class TestCalc(unittest.TestCase):\n"
                "    @unittest.skip('existing skipped test')\n"
                "    def test_skipped(self): self.assertEqual(value(), 2)\n"
                "    def test_active(self): self.assertEqual(value(), 2)\n")
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            subprocess.run(["git", "add", "."], cwd=dest, check=True)
        meta = {"healer":"genesis","target":"eve","repo":repair.REPOS["eve"],"sha":"a"*40}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
                repair, "checkout_target", fake_checkout):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.validate(meta, patch, Path(d)/"verified")

    def test_restricted_auto_repair_rejects_forged_completion_marker(self):
        before = b"def value():\n    return 1\n"
        after = (b"import os, sys\n"
                 b"print('__MUTUAL_HEAL_SUITE_FINISHED__' + sys.argv[1])\n"
                 b"os._exit(0)\n"
                 b"def value():\n    return 1\n")
        with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
            repair.enforce_literal_return_repair(before, after)

    def test_restricted_auto_repair_allows_only_return_literals(self):
        self.assertEqual(repair.enforce_literal_return_repair(
            b"def value():\n    return 1\n",
            b"def value():\n    return 2\n"), 1)
        with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
            repair.enforce_literal_return_repair(
                b"def value():\n    return 1\n",
                b"def value():\n    return os._exit(0)\n")

    def test_fixture_error_finishes_suite_without_auto_attestation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src"/"calc.py").write_text(
                "def boot():\n    raise RuntimeError('broken')\n")
            (root / "tests"/"test_calc.py").write_text(
                "import unittest\nfrom src.calc import boot\n"
                "class TestCalc(unittest.TestCase):\n"
                "    @classmethod\n    def setUpClass(cls): boot()\n"
                "    def test_one(self): self.assertTrue(True)\n"
                "    def test_two(self): self.assertTrue(True)\n")
            run, stats = repair.run_tracked_tests(root)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(stats["executed"], 0)
            self.assertEqual(stats["errors"], 1)
            self.assertEqual(stats["discovered"], 2)

    def test_publisher_independently_rejects_executable_patch(self):
        original = b"def value():\n    return 1\n"
        malicious = b"import os\ndef value():\n    return os._exit(0)\n"
        meta = {"healer": "genesis", "target": "eve", "repo": repair.REPOS["eve"],
                "path": "src/calc.py", "sha": "a"*40, "run_id": 55,
                "run_url": "https://github.com/Maxhm007/Eve/actions/runs/55",
                "new_sha256": hashlib.sha256(malicious).hexdigest(),
                "baseline": "failed", "patched": "passed",
                "tests_completed": True, "tests_executed": 1,
                "test_command": "python -m unittest discover -s tests -v"}
        requests = []
        def fake_api(repo, suffix, method="GET", payload=None, token=""):
            requests.append((method, suffix))
            if method != "GET":
                raise AssertionError("No repository write is allowed")
            return {"encoding": "base64", "sha": "b"*40,
                    "content": base64.b64encode(original).decode()}
        with mock.patch.object(repair, "_api", fake_api):
            with self.assertRaisesRegex(ValueError, "Restricted auto-repair"):
                repair.publish(meta, base64.b64encode(malicious).decode(), "token")
        self.assertEqual([method for method, _ in requests], ["GET"])

    def test_encoding_cookie_bypass_rejected(self):
        original = b"def value():\n    return 1\n"
        attack = (
            b"# coding: unicode_escape\n"
            b"# \\u000aimport os, sys; os._exit(0)\n"
            b"def value():\n    return 2\n"
        )
        with self.assertRaisesRegex(ValueError, "encoding"):
            repair.enforce_literal_return_repair(original, attack)

    def test_second_line_encoding_cookie_rejected(self):
        original = b"def value():\n    return 1\n"
        attack = (b"#!/usr/bin/env python3\n"
                  b"# coding: unicode_escape\n"
                  b"def value():\n    return 2\n")
        with self.assertRaisesRegex(ValueError, "encoding"):
            repair.enforce_literal_return_repair(original, attack)

    def test_bom_and_even_utf8_encoding_declarations_rejected(self):
        original = b"def value():\n    return 1\n"
        candidates = [
            bytes.fromhex("efbbbf") + b"def value():\n    return 2\n",
            b"# coding: utf-8\ndef value():\n    return 2\n",
            b"# -*- coding: latin-1 -*-\ndef value():\n    return 2\n",
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate[:40]):
                with self.assertRaisesRegex(ValueError, "encoding|BOM"):
                    repair.enforce_literal_return_repair(original, candidate)

    def test_safe_unicode_utf8_literal_change_allowed(self):
        before = "def title():\n    return 'café'\n".encode("utf-8")
        after = "def title():\n    return 'naïve'\n".encode("utf-8")
        self.assertEqual(repair.enforce_literal_return_repair(before, after), 1)

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

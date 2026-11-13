"""Offline tests for the LOCAL mutual-healing activation helper."""
import importlib.util
import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


path = Path(__file__).resolve().parents[1] / "scripts" / "activate_mutual_healing.py"
spec = importlib.util.spec_from_file_location("mutual_activation", path)
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class ActivationTests(unittest.TestCase):
    def test_requires_gh_cli(self):
        with patch.object(activation.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Install GitHub CLI"):
                activation.setup()

    def test_aborted_setup_makes_no_changes(self):
        with patch.object(activation.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(activation, "gh") as gh, \
             patch("builtins.input", return_value="NO"):
            self.assertEqual(activation.setup(), 1)
            gh.assert_called_once_with("auth", "status")

    def test_different_tokens_required(self):
        with patch.object(activation.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(activation, "gh") as gh, \
             patch("builtins.input", return_value="ACTIVATE"), \
             patch.object(activation.getpass, "getpass", side_effect=["SAME", "SAME"]):
            with self.assertRaisesRegex(ValueError, "DIFFERENT"):
                activation.setup()
            gh.assert_called_once_with("auth", "status")

    def test_activates_both_only_after_receiving_separate_tokens(self):
        calls = []
        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            return ""
        out = io.StringIO()
        with patch.object(activation.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(activation, "gh", side_effect=runner), \
             patch("builtins.input", return_value="ACTIVATE"), \
             patch.object(activation.getpass, "getpass", side_effect=["EVE_PRIVATE", "GENESIS_PRIVATE"]), \
             redirect_stdout(out):
            self.assertEqual(activation.setup(), 0)
        self.assertEqual(len(calls), 9)
        self.assertEqual(calls[0][0], ("auth", "status"))
        self.assertEqual(calls[1][1]["secret"], "EVE_PRIVATE")
        self.assertEqual(calls[4][1]["secret"], "GENESIS_PRIVATE")
        self.assertEqual([x[0][0:2] for x in calls[-2:]], [
            ("workflow", "run"), ("workflow", "run")
        ])
        self.assertNotIn("EVE_PRIVATE", out.getvalue())
        self.assertNotIn("GENESIS_PRIVATE", out.getvalue())
        self.assertNotIn("MUTUAL_HEAL_REPAIR_ENABLED", str(calls))

    def test_secrets_use_stdin_not_command_line(self):
        captured = {}
        def fake_run(argv, **kwargs):
            captured.update({"argv": argv, **kwargs})
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")
        with patch.object(activation.subprocess, "run", side_effect=fake_run):
            self.assertEqual(activation.gh("secret", "set", "PEER_HEAL_TOKEN", secret="SECRET"), "ok")
        self.assertNotIn("SECRET", captured["argv"])
        self.assertEqual(captured["input"], "SECRET\n")


if __name__ == "__main__":
    unittest.main()

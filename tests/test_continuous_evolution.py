"""No-network tests for the Nexus-owned continuous evolution ledger."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock


def load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "continuous_evolution.py"
    spec = importlib.util.spec_from_file_location("continuous_nexus", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


m = load()


class LedgerTests(TestCase):
    def setUp(self):
        self.body = (m.START + "\n" + m.FENCE + "json\n" +
                     json.dumps({"version": 1, "sequence": 1, "owner": "genesis",
                                 "status": "ready", "lease_until": None,
                                 "last_result": "bootstrap"}) +
                     "\n" + m.FENCE + "\n" + m.END)

    def test_state_roundtrip(self):
        state = m.decode(self.body)
        self.assertEqual(state["sequence"], 1)
        self.assertEqual(m.decode(m.encode(self.body, state)), state)

    def test_rejects_corrupt_ledger(self):
        with self.assertRaises(ValueError):
            m.decode(self.body.replace(m.START, "missing"))
        with self.assertRaises(ValueError):
            m.decode(m.encode(self.body, {"version": 1, "sequence": 0,
                                          "owner": "eve", "status": "ready"}))

    def test_genesis_turn_runs_once_then_assigns_eve(self):
        store = {"body": self.body}
        actions = []
        def fake_api(repo, suffix, method="GET", payload=None, token=""):
            self.assertEqual(repo, m.GENESIS)
            if method == "PATCH":
                actions.append(payload)
                store["body"] = payload["body"]
                return {}
            return store
        worker = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with mock.patch.object(m, "api", side_effect=fake_api):
            self.assertEqual(m.tick("local", work=worker), "genesis teammate exit 0")
        worker.assert_called_once()
        state = m.decode(store["body"])
        self.assertEqual((state["sequence"], state["owner"], state["status"]),
                         (2, "eve", "ready"))
        self.assertEqual(len(actions), 2)

    def test_eve_turn_ack_advances_once(self):
        state = {"version": 1, "sequence": 2, "owner": "eve", "status": "running",
                 "lease_until": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        store = {"body": m.encode(self.body, state)}
        acknowledgement = ("<!-- continuous-eve-ack -->\n" + m.FENCE +
                           'json\n{"version":1,"sequence":2,"status":"completed","run_url":"https://github.com/Maxhm007/Eve/actions/runs/12345"}\n' +
                           m.FENCE + "\n<!-- /continuous-eve-ack -->")
        def fake_api(repo, suffix, method="GET", payload=None, token=""):
            if repo == m.EVE:
                if suffix == "/actions/runs/12345":
                    return {"id": 12345, "name": "Eve Continuous Evolution — Peer Turn",
                            "head_branch": "main", "status": "completed",
                            "conclusion": "success", "event": "schedule"}
                return {"body": acknowledgement}
            if method == "PATCH":
                store["body"] = payload["body"]
                return {}
            return store
        worker = mock.Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
        with mock.patch.object(m, "api", side_effect=fake_api):
            self.assertEqual(m.tick("local", work=worker), "genesis teammate exit 0")
        worker.assert_called_once()
        self.assertEqual(m.decode(store["body"])["sequence"], 4)
        self.assertEqual(m.decode(store["body"])["owner"], "eve")

    def test_eve_receipt_rejected_if_actions_run_not_successful(self):
        receipt = ("<!-- continuous-eve-ack -->\n" + m.FENCE +
                   'json\n{"version":1,"sequence":2,"status":"completed","run_url":"https://github.com/Maxhm007/Eve/actions/runs/12345"}\n' +
                   m.FENCE + "\n<!-- /continuous-eve-ack -->")
        def api(repo, suffix, method="GET", payload=None, token=""):
            self.assertEqual(repo, m.EVE)
            if suffix == "/issues/39":
                return {"body": receipt}
            if suffix == "/actions/runs/12345":
                return {"id": 12345, "name": "Eve Continuous Evolution — Peer Turn",
                        "head_branch": "main", "status": "completed",
                        "conclusion": "failure", "event": "schedule"}
            raise AssertionError("Unexpected request")
        with mock.patch.object(m, "api", side_effect=api):
            self.assertFalse(m.ack_exists(2))

    def test_eve_receipt_rejected_if_url_untrusted(self):
        receipt = ("<!-- continuous-eve-ack -->\n" + m.FENCE +
                   'json\n{"version":1,"sequence":2,"status":"completed","run_url":"https://evil.invalid/run/12345"}\n' +
                   m.FENCE + "\n<!-- /continuous-eve-ack -->")
        with mock.patch.object(m, "api", return_value={"body": receipt}) as api:
            self.assertFalse(m.ack_exists(2))
        api.assert_called_once_with(m.EVE, "/issues/39")

    def test_expired_eve_turn_recovers(self):
        state = {"version": 1, "sequence": 2, "owner": "eve", "status": "running",
                 "lease_until": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}
        store = {"body": m.encode(self.body, state)}
        def fake_api(repo, suffix, method="GET", payload=None, token=""):
            if repo == m.EVE:
                return {"body": "<!-- continuous-eve-ack -->\n" + m.FENCE +
                        'json\n{"version":1,"sequence":0,"status":"initial"}\n' +
                        m.FENCE + "\n<!-- /continuous-eve-ack -->"}
            if method == "PATCH":
                store["body"] = payload["body"]
                return {}
            return store
        with mock.patch.object(m, "api", side_effect=fake_api):
            self.assertEqual(m.tick("local"), "eve_lease_expired")
        self.assertEqual(m.decode(store["body"])["owner"], "genesis")

    def test_nonzero_genesis_exit_has_explicit_failure_category(self):
        store = {"body": self.body}
        def fake_api(repo, suffix, method="GET", payload=None, token=""):
            if method == "PATCH":
                store["body"] = payload["body"]
                return {}
            return store
        failed = mock.Mock(return_value=SimpleNamespace(
            returncode=1, stdout="", stderr="Traceback (most recent call last)"))
        with mock.patch.object(m, "api", side_effect=fake_api):
            result = m.tick("local", work=failed)
        self.assertEqual(result, "genesis teammate exit 1; category=traceback")
        self.assertIn("category=traceback", m.decode(store["body"])["last_result"])
        self.assertEqual(m.decode(store["body"])["owner"], "eve")

    def test_no_peer_write_authority(self):
        with self.assertRaises(ValueError):
            m.api(m.EVE, "/issues/39", method="PATCH",
                  payload={"body": "unsafe"}, token="local")

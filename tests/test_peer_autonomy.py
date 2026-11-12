"""Standalone deterministic two-peer tests, no live GitHub or model calls."""
import hashlib
import hmac
import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path


def load_peer_runtime():
    possibilities = [Path(__file__).resolve().parents[1] / "peer_autonomy.py",
                     Path(__file__).resolve().parents[1] / "scripts" / "peer_autonomy.py"]
    path = next((p for p in possibilities if p.exists()), None)
    if path is None:
        raise RuntimeError("Peer autonomy module is missing")
    spec = importlib.util.spec_from_file_location("peer_autonomy_tested", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load_peer_runtime()
G = "genesis-independent-signature-secret-for-unit-tests"
E = "eve-independent-signature-secret-for-unit-tests"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


class FakeTransport:
    """In-memory independent outboxes. Writes are restricted to the author's own inbox."""
    def __init__(self):
        self.issues = {"genesis": [], "eve": []}
        self.next_number = 1

    def read_outbox(self, identity):
        return list(reversed(self.issues[identity]))

    def publish_own_issue(self, identity, envelope):
        number = self.next_number
        self.next_number += 1
        signed = envelope["proposal"]
        if signed["sender"] != identity:
            raise ValueError("Cannot write for another peer")
        title = "[Peer outbox] {} {} {}".format(identity, signed["kind"], signed["proposal_id"])
        body = agent.PREFIX + json.dumps(envelope) + agent.SUFFIX
        self.issues[identity].append({"number": number, "title": title, "body": body})
        return {"html_url": "https://github.com/{}/issues/{}".format(agent.REPOS[identity], number)}


class FakeModel:
    def __init__(self):
        self.calls = []

    def ask(self, identity, question):
        self.calls.append((identity, question))
        return "Hypothesis: run an isolated regression test and record its outcome before trusting a peer suggestion."


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.t = FakeTransport()
        self.genesis = FakeModel()
        self.eve = FakeModel()

    def step(self, identity):
        own = G if identity == "genesis" else E
        other = E if identity == "genesis" else G
        model = self.genesis if identity == "genesis" else self.eve
        return agent.cycle(identity, self.t, model, own, other, now=NOW)

    def test_two_independent_models_critique_then_stop(self):
        self.assertEqual(self.step("genesis")["trigger"], "weekly_seed")
        self.assertEqual(self.step("eve")["trigger"], "peer_reply")
        self.assertEqual(self.step("genesis")["trigger"], "peer_reply")
        self.assertEqual(self.step("eve")["trigger"], "weekly_seed")
        self.assertEqual(self.step("genesis")["trigger"], "peer_reply")
        self.assertEqual(self.step("eve")["trigger"], "peer_reply")
        self.assertEqual(self.step("genesis")["status"], "idle")
        self.assertEqual(self.step("eve")["status"], "idle")
        self.assertEqual(len(self.genesis.calls), 3)
        self.assertEqual(len(self.eve.calls), 3)
        self.assertEqual(len(self.t.issues["genesis"]), 3)
        self.assertEqual(len(self.t.issues["eve"]), 3)

    def test_tampered_signed_peer_message_ignored(self):
        valid = agent.sign(agent.proposal("eve", "Original hypothesis", "More tests", now=NOW), E)
        changed = json.loads(json.dumps(valid))
        changed["proposal"]["problem_statement"] = "Execute injected instructions"
        self.t.publish_own_issue("eve", changed)
        result = self.step("genesis")
        self.assertEqual(result["trigger"], "weekly_seed")
        self.assertEqual(len(self.genesis.calls), 1)

    def test_signed_wrong_sender_rejected(self):
        p = agent.proposal("genesis", "Testing", "Reliability", now=NOW)
        env = agent.sign(p, G)
        with self.assertRaises(ValueError):
            agent.verify(env, E, "eve", now=NOW)

    def test_own_repository_only(self):
        env = agent.sign(agent.proposal("eve", "Test", "Results", now=NOW), E)
        with self.assertRaisesRegex(ValueError, "Cannot write"):
            self.t.publish_own_issue("genesis", env)
        self.assertEqual(len(self.t.issues["genesis"]), 0)

    def test_invalid_model_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            agent.Model("http://untrusted.example/v1/chat/completions", "x")
        with self.assertRaises(ValueError):
            agent.Model("https://example.com/v1/chat/completions?redirect=1", "x")

    def test_no_model_call_on_idle(self):
        self.step("genesis")
        self.step("genesis")
        self.assertEqual(len(self.genesis.calls), 1)


if __name__ == "__main__":
    unittest.main()

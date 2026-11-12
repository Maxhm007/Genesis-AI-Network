"""Standalone deterministic two-peer tests, no live GitHub or model calls."""
import hashlib
import hmac
import importlib.util
import json
import unittest
import urllib.error
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

    def test_outbox_paginates_before_deduping(self):
        fresh = datetime.now(timezone.utc).isoformat()
        ignored = [{"title": "Ordinary issue", "created_at": fresh} for _ in range(20)]
        own = agent.sign(agent.proposal("genesis", "A", "B", now=datetime.now(timezone.utc)), G)
        stored = {"title": "[Peer outbox] genesis hypothesis " + own["proposal"]["proposal_id"],
                  "body": agent.PREFIX + json.dumps(own) + agent.SUFFIX,
                  "created_at": fresh}
        class MockTransport(agent.Transport):
            def __init__(self):
                super().__init__("token")
                self.pages = []
            def _request(self, url, method="GET", payload=None):
                self.pages.append(url)
                if "&page=1" in url: return ignored
                if "&page=2" in url: return [stored]
                return []
        transport = MockTransport()
        result = transport.read_outbox("genesis")
        self.assertEqual(len(result), 21)
        self.assertEqual(len(transport.pages), 2)

    def test_malicious_nested_json_cannot_stop_cycle(self):
        nested = "[" * 2000 + "0" + "]" * 2000
        bad = {"title": "[Peer outbox] eve hypothesis invalid",
               "body": agent.PREFIX + nested + agent.SUFFIX}
        self.t.issues["eve"].append(bad)
        self.assertEqual(self.step("genesis")["trigger"], "weekly_seed")

    def test_peer_outage_does_not_block_self_research(self):
        class PeerOffline(FakeTransport):
            def read_outbox(self, identity):
                if identity == "eve":
                    raise urllib.error.URLError("Peer unavailable")
                return super().read_outbox(identity)
        self.t = PeerOffline()
        result = self.step("genesis")
        self.assertEqual(result["trigger"], "weekly_seed")
        self.assertEqual(len(self.genesis.calls), 1)

    def test_no_model_call_on_idle(self):
        self.step("genesis")
        self.step("genesis")
        self.assertEqual(len(self.genesis.calls), 1)


if __name__ == "__main__":
    unittest.main()

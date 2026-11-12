"""Isolated stdlib tests: python -m unittest discover -s tests -p test_eve_peer_bridge.py"""
import importlib.util
import io
import json
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "eve_peer_bridge.py"
SPEC = importlib.util.spec_from_file_location("eve_peer_bridge", PATH)
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
KEY = "example-only-not-real-peer-secret-1234567890"


class FakeResponse:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return io.BytesIO(json.dumps(self.value).encode())
    def __exit__(self, *args):
        return False


class ProtocolTests(unittest.TestCase):
    def test_create_and_sign(self):
        p = peer.proposal("hypothesis", "Test question", "Test benefit")
        envelope = peer.sign(p, KEY)
        self.assertEqual(envelope["proposal"]["sender"], "genesis")

    def test_github_send_posts_to_eve(self):
        messages = []
        def opener(req, timeout):
            messages.append(req)
            return FakeResponse({"html_url": "https://github.com/Maxhm007/Eve/issues/5", "number": 5})
        envelope = peer.sign(peer.proposal("test", "Test issue", "Better science"), KEY)
        receipt = peer.send(envelope, KEY, "token", opener=opener)
        self.assertEqual(receipt["issue_number"], 5)
        self.assertEqual(messages[0].get_method(), "POST")
        self.assertIn("/Maxhm007/Eve/issues", messages[0].full_url)

    def test_tampered_envelope_rejected(self):
        envelope = peer.sign(peer.proposal("critique", "Question", "Test"), KEY)
        envelope["proposal"]["problem_statement"] = "Changed"
        with self.assertRaises(ValueError):
            peer.send(envelope, KEY, "token", opener=lambda req, timeout: self.fail("Sent invalid"))

    def test_receiver_rejects_wrong_direction(self):
        envelope = peer.sign(peer.proposal("hypothesis", "Question", "Test"), KEY)
        with self.assertRaises(ValueError):
            peer.verify(envelope, KEY, recipient="genesis")


if __name__ == "__main__":
    unittest.main()

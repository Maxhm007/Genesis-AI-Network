from __future__ import annotations

import tempfile
import unittest

from genesis.peers import PeerClient, PeerStatusServer
from genesis.providers import ProviderRegistry
from genesis.team import AITeam


class FakeProvider:
    name = "fake-provider"

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        return "candidate analysis: " + prompt.splitlines()[0]


class TeamAndPeerTests(unittest.TestCase):
    def test_ai_team_routes_roles_to_available_provider(self):
        registry = ProviderRegistry(include_bootstrap=False)
        registry.register(FakeProvider())
        outputs = AITeam(registry).run_task("test objective")
        self.assertGreaterEqual(len(outputs), 8)
        self.assertTrue(all(item["status"] == "completed" for item in outputs))
        self.assertTrue(all(item["provider"] == "fake-provider" for item in outputs))

    def test_ai_team_waits_safely_without_provider(self):
        registry = ProviderRegistry(include_bootstrap=False)
        outputs = AITeam(registry).run_task("test objective")
        self.assertGreaterEqual(len(outputs), 8)
        self.assertTrue(all(item["status"] == "waiting_for_provider" for item in outputs))

    def test_second_node_compatibility_probe(self):
        constitution_hash = "a" * 64
        server = PeerStatusServer(
            "127.0.0.1",
            0,
            lambda: {
                "network": "Genesis AI Network",
                "version": "0.1.0",
                "node_id": "node-two",
                "constitution_sha256": constitution_hash,
                "operating_mode": "maintenance",
            },
        )
        server.start()
        try:
            host, port = server.address
            record = PeerClient(timeout=2).probe(f"http://{host}:{port}", constitution_hash)
            self.assertEqual(record.node_id, "node-two")
            self.assertEqual(record.status, "compatible")
        finally:
            server.stop()

    def test_constitution_mismatch_is_not_compatible(self):
        server = PeerStatusServer(
            "127.0.0.1",
            0,
            lambda: {"node_id": "foreign-node", "constitution_sha256": "b" * 64},
        )
        server.start()
        try:
            host, port = server.address
            record = PeerClient(timeout=2).probe(f"http://{host}:{port}", "a" * 64)
            self.assertEqual(record.status, "constitution_mismatch")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

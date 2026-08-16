from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from genesis.node import GenesisNode
from genesis.providers import ProviderRegistry


CONSTITUTION = "immutable-test-constitution\n"


class FakeProvider:
    def __init__(self, name: str, is_available: bool) -> None:
        self.name = name
        self._is_available = is_available

    def available(self) -> bool:
        return self._is_available

    def reason(self, prompt: str) -> str:
        return "ok"


class ProviderModeTests(unittest.TestCase):
    def make_root(self, temp: str) -> Path:
        root = Path(temp)
        constitution_path = root / "GENESIS_CONSTITUTION.md"
        constitution_path.write_text(CONSTITUTION, encoding="utf-8")
        digest = hashlib.sha256(constitution_path.read_bytes()).hexdigest()
        (root / "GENESIS_BLOCK.json").write_text(
            json.dumps({"constitution": {"sha256": digest}}), encoding="utf-8"
        )
        return root

    def test_maintenance_mode_with_explicitly_empty_provider_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_root(temp)
            registry = ProviderRegistry(include_bootstrap=False)
            node = GenesisNode(root, db_path=root / "state.db", providers=registry)
            node.verify_constitution()
            self.assertEqual(node.refresh_operating_mode(), "maintenance")
            node.conn.close()

    def test_default_node_has_native_bootstrap_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_root(temp)
            node = GenesisNode(root, db_path=root / "state.db")
            node.verify_constitution()
            self.assertEqual(node.refresh_operating_mode(), "active")
            node.conn.close()

    def test_active_mode_with_available_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_root(temp)
            registry = ProviderRegistry(include_bootstrap=False)
            registry.register(FakeProvider("fake", True))
            node = GenesisNode(root, db_path=root / "state.db", providers=registry)
            node.verify_constitution()
            self.assertEqual(node.refresh_operating_mode(), "active")
            node.conn.close()


if __name__ == "__main__":
    unittest.main()

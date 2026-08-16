import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from genesis.evolution import EvolutionManager
from genesis.knowledge import KnowledgeStore


class AutonomyCycleTests(unittest.TestCase):
    def test_candidate_knowledge_is_not_trusted_automatically(self):
        conn = sqlite3.connect(":memory:")
        store = KnowledgeStore(conn)
        digest = store.add_candidate("example claim", "unit-test", "test")
        row = conn.execute("SELECT status FROM knowledge WHERE content_hash=?", (digest,)).fetchone()
        self.assertEqual(row[0], "candidate")

    def test_evolution_proposal_stays_candidate(self):
        conn = sqlite3.connect(":memory:")
        with tempfile.TemporaryDirectory() as tmp:
            manager = EvolutionManager(Path(tmp), conn)
            candidate_id = manager.propose("test", "validate isolation", {"file": "candidate"})
            self.assertTrue(manager.validate_structure(candidate_id))
            row = conn.execute("SELECT status FROM evolution_candidates WHERE id=?", (candidate_id,)).fetchone()
            self.assertEqual(row[0], "candidate")


if __name__ == "__main__":
    unittest.main()

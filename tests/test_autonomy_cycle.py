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

    def test_invalid_evolution_proposal_json_fails_closed_and_records_validation(self):
        conn = sqlite3.connect(":memory:")
        with tempfile.TemporaryDirectory() as tmp:
            manager = EvolutionManager(Path(tmp), conn)
            candidate_id = manager.propose("test", "reject malformed proposal", {"file": "candidate"})
            row = conn.execute(
                "SELECT proposal_path FROM evolution_candidates WHERE id=?",
                (candidate_id,),
            ).fetchone()
            Path(row[0]).write_text("{not-json", encoding="utf-8")

            self.assertFalse(manager.validate_structure(candidate_id))

            status, validation = conn.execute(
                "SELECT status,validation FROM evolution_candidates WHERE id=?",
                (candidate_id,),
            ).fetchone()
            self.assertEqual(status, "candidate")
            self.assertIsInstance(validation, str)
            self.assertTrue(validation)
            details = json.loads(validation)
            self.assertFalse(details["structural_validation"])
            self.assertTrue(details.get("error"))


if __name__ == "__main__":
    unittest.main()

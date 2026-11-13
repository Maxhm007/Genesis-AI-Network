"""Security and bounded recovery tests for reciprocal healer."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load():
    here = Path(__file__).resolve().parents[1]
    module = here / "mutual_healer.py"
    if not module.exists():
        module = here / "scripts" / "mutual_healer.py"
    spec = importlib.util.spec_from_file_location("mutual_healer_tested", module)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


heal = load()
NOW = datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc)


def run(number=31, attempt=1, hours=1, name="CI tests"):
    return {"id": number, "run_attempt": attempt, "status": "completed",
            "conclusion": "failure", "name": name,
            "created_at": (NOW-timedelta(hours=hours)).isoformat(),
            "html_url": "https://github.com/Maxhm007/Eve/actions/runs/" + str(number)}


class API:
    def __init__(self, runs=None, ticket_exists=False):
        self.runs = list(runs or [])
        self.ticket_exists = ticket_exists
        self.retried = []
        self.created = []

    def failed_runs(self, target):
        return self.runs

    def retry_failed(self, target, identifier):
        self.retried.append((target, identifier))

    def jobs(self, target, identifier):
        return [{"conclusion": "failure", "name": "test",
                 "steps": [{"name": "Run unit tests", "conclusion": "failure"},
                           {"name": "Setup", "conclusion": "success"}]}]

    def find_ticket(self, target, title):
        return self.ticket_exists

    def issue(self, target, title, body):
        self.created.append((target, title, body))
        return {"html_url": "https://github.com/Maxhm007/Eve/issues/55"}


class MutualTests(unittest.TestCase):
    def test_first_failure_requests_one_retry(self):
        api = API([run(), run(32, attempt=1, hours=2)])
        outcome = heal.heal_once("genesis", api, NOW)
        self.assertEqual(outcome["status"], "recovery_retry_requested")
        self.assertEqual(api.retried, [("eve", 31)])
        self.assertFalse(api.created)

    def test_second_failure_creates_evidence_ticket(self):
        api = API([run(attempt=2)])
        result = heal.heal_once("genesis", api, NOW)
        self.assertEqual(result["status"], "repair_ticket_created")
        self.assertEqual(api.created[0][0], "eve")
        self.assertIn("Run unit tests", api.created[0][2])
        self.assertIn("A verified code fix has NOT been applied", api.created[0][2])

    def test_existing_ticket_is_not_duplicated(self):
        api = API([run(attempt=2)], ticket_exists=True)
        result = heal.heal_once("eve", api, NOW)
        self.assertEqual(result["status"], "repair_tickets_already_open")
        self.assertFalse(api.created)

    def test_existing_ticket_does_not_block_later_failure(self):
        api = API([run(31, attempt=2), run(30, attempt=1, hours=3)],
                  ticket_exists=True)
        result = heal.heal_once("genesis", api, NOW)
        self.assertEqual(result["run_id"], 30)
        self.assertEqual(api.retried, [("eve", 30)])

    def test_ten_existing_tickets_do_not_starve_older_failure(self):
        reports = [run(200+i, attempt=2, hours=1+i/5) for i in range(10)]
        older = run(11, attempt=1, hours=5)
        api = API(reports + [older], ticket_exists=True)
        result = heal.heal_once("eve", api, NOW)
        self.assertEqual(result["status"], "recovery_retry_requested")
        self.assertEqual(api.retried, [("genesis", 11)])

    def test_old_and_cancelled_runs_ignored(self):
        api = API([run(hours=55), {**run(42), "conclusion": "cancelled"}])
        result = heal.heal_once("genesis", api, NOW)
        self.assertEqual(result["status"], "healthy_or_no_recent_failed_runs")
        self.assertFalse(api.retried)

    def test_legacy_chatter_not_retried(self):
        api = API([run(name="Eve independent peer research")])
        self.assertFalse(heal.select_failure(api.runs, NOW))

    def test_eve_repairs_genesis_only(self):
        api = API([run()])
        result = heal.heal_once("eve", api, NOW)
        self.assertEqual(result["target"], "genesis")
        self.assertEqual(api.retried, [("genesis", 31)])

    def test_target_write_allowlist(self):
        with self.assertRaises(ValueError):
            heal.GitHub("test-token", opener=lambda *_: None).request(
                "POST", "genesis", "/contents/scripts/example.py", {"content": "malicious"})
        with self.assertRaises(ValueError):
            heal.GitHub("test-token", opener=lambda *_: None).request(
                "POST", "genesis", "/actions/workflows/12/enable")

    def test_missing_cross_repository_credentials_fail_closed(self):
        with self.assertRaises(ValueError):
            heal.GitHub("")


    def test_local_recovery_uses_own_repository(self):
        api = API([run()])
        result = heal.heal_once("eve", api, NOW, target="eve")
        self.assertEqual(result["target"], "eve")
        self.assertEqual(api.retried, [("eve", 31)])

    def test_local_github_token_cannot_touch_peer(self):
        api = heal.LocalGitHub("github-actions-token", "eve", opener=lambda *_: None)
        with self.assertRaisesRegex(ValueError, "peer"):
            api.request("POST", "genesis", "/issues", {"title": "attack"})
        with self.assertRaisesRegex(ValueError, "peer"):
            api.request("POST", "genesis", "/actions/runs/3/rerun-failed-jobs")
        with self.assertRaisesRegex(ValueError, "peer"):
            api.request("GET", "genesis", "/actions/runs?status=failure")

    def test_local_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            heal.LocalGitHub("token", "unknown")
        with self.assertRaises(ValueError):
            heal.heal_once("eve", API(), NOW, target="unknown")

    def test_self_healing_workflow_never_retries_itself(self):
        self.assertEqual(heal.select_failure([run(name="Eve self-healing watchdog")], NOW), [])
        self.assertEqual(heal.select_failure([run(name="Genesis self-healing watchdog")], NOW), [])

    def test_missing_attempt_disables_retry(self):
        self.assertEqual(heal.select_failure([{k:v for k,v in run().items() if k!="run_attempt"}], NOW), [])


if __name__ == "__main__":
    unittest.main()

from pathlib import Path

from scripts import file_self_review_worker as worker


class _FakeProvider:
    name = "fake-provider"


class _FakeCoding:
    def __init__(self, root):
        self.root = Path(root)
        self.providers = object()

    def _provider(self):
        return _FakeProvider()


class _FakeAttempt:
    feedback = None
    status = "iterative_trials_failed"

    def as_dict(self):
        return {"status": self.status}


class _FakeFeedback:
    def __init__(self, *, success: bool = False, failure: str = "test failure"):
        self.candidate_created = success
        self.tests_passed = success
        self.commit_sha = "abc123" if success else None
        self.branch = "genesis/candidate-test" if success else ""
        self.failure = "" if success else failure


class _FakeSuccessfulAttempt(_FakeAttempt):
    feedback = _FakeFeedback(success=True)
    status = "candidate_created"


class _FakeDevLab:
    last_init = None
    last_call = None
    calls = []

    def __init__(self, root, providers):
        type(self).last_init = {"root": Path(root), "providers": providers}
        type(self).calls = []

    def attempt_problem(self, **kwargs):
        type(self).last_call = kwargs
        type(self).calls.append(kwargs)
        return _FakeAttempt()


class _FakeRecoveryDevLab(_FakeDevLab):
    def attempt_problem(self, **kwargs):
        type(self).last_call = kwargs
        type(self).calls.append(kwargs)
        if len(type(self).calls) == 1:
            failed = _FakeAttempt()
            failed.feedback = _FakeFeedback(failure="first attempt failed")
            return failed
        return _FakeSuccessfulAttempt()


def _write_challenge(root: Path, *, status: str = "active", with_ephemeral: bool = False) -> None:
    (root / "genesis").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "genesis" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    ephemeral = (
        ',\n  "ephemeral_acceptance_files": {"tests/test_sample_acceptance.py": "def test_acceptance():\\n    assert True\\n"}'
        if with_ephemeral
        else ""
    )
    (root / "config" / "genesis_challenge.json").write_text(
        "{\n"
        f'  "status": "{status}",\n'
        '  "target": "genesis/sample.py",\n'
        '  "problem": "VALUE should satisfy the assigned behavior",\n'
        '  "acceptance": "The assigned behavior is satisfied",\n'
        '  "method": "correctness_first"'
        f"{ephemeral}\n"
        "}\n",
        encoding="utf-8",
    )


def test_active_assigned_challenge_routes_through_iterative_devlab(tmp_path, monkeypatch):
    _write_challenge(tmp_path, with_ephemeral=True)
    monkeypatch.setattr(worker, "CodingModule", _FakeCoding)
    monkeypatch.setattr(worker, "IterativeGenesisDevLab", _FakeDevLab)

    result = worker._run_assigned_challenge(tmp_path)

    assert result is not None
    spec, attempt = result
    assert isinstance(attempt, _FakeAttempt)
    assert spec["target"] == "genesis/sample.py"
    assert worker.MAX_ASSIGNED_CHALLENGE_ATTEMPTS == 2
    assert len(_FakeDevLab.calls) == worker.MAX_ASSIGNED_CHALLENGE_ATTEMPTS
    assert [call["attempt"] for call in _FakeDevLab.calls] == list(range(worker.MAX_ASSIGNED_CHALLENGE_ATTEMPTS))
    assert _FakeDevLab.calls[0]["previous_error"] == ""
    assert _FakeDevLab.calls[1]["previous_error"] == "iterative_trials_failed"
    assert _FakeDevLab.last_call["target_path"] == "genesis/sample.py"
    assert _FakeDevLab.last_call["acceptance"] == "The assigned behavior is satisfied"
    assert "correctness_first" in _FakeDevLab.last_call["problem"]
    assert _FakeDevLab.last_call["provider"].name == "fake-provider"
    assert _FakeDevLab.last_call["provenance"]["designer"] == "genesis.devlab"
    assert _FakeDevLab.last_call["provenance"]["executor"] == "genesis.devlab"
    assert _FakeDevLab.last_call["provenance"]["attribution"] == "owner_initiated"
    assert _FakeDevLab.last_call["ephemeral_files"] == {
        "tests/test_sample_acceptance.py": "def test_acceptance():\n    assert True\n"
    }


def test_assigned_challenge_stops_retrying_after_candidate_is_created(tmp_path, monkeypatch):
    _write_challenge(tmp_path)
    monkeypatch.setattr(worker, "CodingModule", _FakeCoding)
    monkeypatch.setattr(worker, "IterativeGenesisDevLab", _FakeRecoveryDevLab)

    result = worker._run_assigned_challenge(tmp_path)

    assert result is not None
    _spec, attempt = result
    assert attempt.status == "candidate_created"
    assert len(_FakeRecoveryDevLab.calls) == 2
    assert _FakeRecoveryDevLab.calls[0]["attempt"] == 0
    assert _FakeRecoveryDevLab.calls[1]["attempt"] == 1
    assert _FakeRecoveryDevLab.calls[1]["previous_error"] == "first attempt failed"


def test_inactive_assigned_challenge_does_not_run_devlab(tmp_path, monkeypatch):
    _write_challenge(tmp_path, status="complete")
    monkeypatch.setattr(worker, "CodingModule", _FakeCoding)
    monkeypatch.setattr(worker, "IterativeGenesisDevLab", _FakeDevLab)

    assert worker._run_assigned_challenge(tmp_path) is None

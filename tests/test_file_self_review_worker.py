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

    def as_dict(self):
        return {"status": "iterative_trials_failed"}


class _FakeDevLab:
    last_init = None
    last_call = None

    def __init__(self, root, providers):
        type(self).last_init = {"root": Path(root), "providers": providers}

    def attempt_problem(self, **kwargs):
        type(self).last_call = kwargs
        return _FakeAttempt()


def _write_challenge(root: Path, *, status: str = "active") -> None:
    (root / "genesis").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "genesis" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "config" / "genesis_challenge.json").write_text(
        "{\n"
        f'  "status": "{status}",\n'
        '  "target": "genesis/sample.py",\n'
        '  "problem": "VALUE should satisfy the assigned behavior",\n'
        '  "acceptance": "The assigned behavior is satisfied",\n'
        '  "method": "correctness_first"\n'
        "}\n",
        encoding="utf-8",
    )


def test_active_assigned_challenge_routes_through_iterative_devlab(tmp_path, monkeypatch):
    _write_challenge(tmp_path)
    monkeypatch.setattr(worker, "CodingModule", _FakeCoding)
    monkeypatch.setattr(worker, "IterativeGenesisDevLab", _FakeDevLab)

    result = worker._run_assigned_challenge(tmp_path)

    assert result is not None
    spec, attempt = result
    assert isinstance(attempt, _FakeAttempt)
    assert spec["target"] == "genesis/sample.py"
    assert _FakeDevLab.last_call["target_path"] == "genesis/sample.py"
    assert _FakeDevLab.last_call["acceptance"] == "The assigned behavior is satisfied"
    assert "correctness_first" in _FakeDevLab.last_call["problem"]
    assert _FakeDevLab.last_call["provider"].name == "fake-provider"
    assert _FakeDevLab.last_call["provenance"]["designer"] == "genesis.devlab"
    assert _FakeDevLab.last_call["provenance"]["executor"] == "genesis.devlab"
    assert _FakeDevLab.last_call["provenance"]["attribution"] == "owner_initiated"


def test_inactive_assigned_challenge_does_not_run_devlab(tmp_path, monkeypatch):
    _write_challenge(tmp_path, status="complete")
    monkeypatch.setattr(worker, "CodingModule", _FakeCoding)
    monkeypatch.setattr(worker, "IterativeGenesisDevLab", _FakeDevLab)

    assert worker._run_assigned_challenge(tmp_path) is None

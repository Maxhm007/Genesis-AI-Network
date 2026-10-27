import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / ".github/workflows/gate/protected_gate.py"


def _gate():
    spec = importlib.util.spec_from_file_location("protected_gate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path):
    root = tmp_path / "repo"
    real = Path(__file__).resolve().parents[1]
    (root / "genesis").mkdir(parents=True)
    (root / ".github/workflows/gate").mkdir(parents=True)
    for name in ("log_redaction.py", "change_review.py"):
        (root / "genesis" / name).write_bytes((real / "genesis" / name).read_bytes())
    (root / "genesis/selfdev.py").write_text("LOCKED = True\n")
    (root / "genesis/tool.py").write_text("def f():\n    return 1\n")
    (root / ".github/workflows/genesis-protected-gate.yml").write_text("permissions:\n  actions: write\n")
    (root / ".github/workflows/ok.yml").write_text("permissions:\n  contents: read\n")
    files = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
             for p in ("genesis/log_redaction.py", "genesis/change_review.py", "genesis/selfdev.py")}
    (root / ".github/workflows/gate/manifest.json").write_text(json.dumps({"files": files}))
    _git(root, "init", "-q")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    return root


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=Maxhm007", "-c", "user.email=x@x", "commit", "-qm", message)


def test_clean_repo_passes(tmp_path):
    root = _repo(tmp_path)
    result = _gate().run(root, None, 5)
    assert result["reviewer_loaded"] and not result["hashes"] and not result["commits"]
    assert not result["workflows"]


def test_locked_change_flagged_even_with_human_author(tmp_path):
    root = _repo(tmp_path)
    (root / "genesis/selfdev.py").write_text("LOCKED = False\n")
    _commit(root, "looks human")
    result = _gate().run(root, None, 5)
    assert any("genesis/selfdev.py" in row for row in result["hashes"])
    assert any("without updating the manifest" in row for row in result["commits"])


def test_risky_code_in_unlocked_file_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "genesis/tool.py").write_text("import subprocess\n\ndef f():\n    return subprocess.run(['x'])\n")
    _commit(root, "tool change")
    result = _gate().run(root, None, 5)
    assert any("subprocess" in row for row in result["commits"])


def test_tampered_reviewer_is_not_loaded(tmp_path):
    root = _repo(tmp_path)
    (root / "genesis/change_review.py").write_text("def review_change(*a):\n    return []\n")
    _commit(root, "quiet reviewer")
    result = _gate().run(root, None, 5)
    assert not result["reviewer_loaded"]
    assert "WOULD FAIL" in _gate().render(result, True)


def test_actions_write_outside_gate_reported(tmp_path):
    root = _repo(tmp_path)
    (root / ".github/workflows/ok.yml").write_text("permissions:\n  actions: write\n")
    _commit(root, "widen")
    result = _gate().run(root, None, 5)
    assert result["workflows"] == ["workflow other than the gate has actions: write: .github/workflows/ok.yml"]


def test_manifest_matches_locked_paths():
    root = Path(__file__).resolve().parents[1]
    import genesis.selfdev as selfdev
    manifest = json.loads((root / ".github/workflows/gate/manifest.json").read_text())
    assert set(manifest["files"]) == set(selfdev.PROTECTED_PATHS)
    assert _gate().check_hashes(root, manifest) == []

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision_gden_identities.py"
spec = importlib.util.spec_from_file_location("provision_gden_identities", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_generate_identity_is_ed25519_raw_public_key() -> None:
    identity = module.generate_identity("peer", "owner/repo")
    assert identity.private_pem.startswith("-----BEGIN")
    assert len(base64.b64decode(identity.public_key_b64, validate=True)) == 32


def test_dry_run_never_requires_github(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("GitHub must not be called in dry-run")

    monkeypatch.setattr(module, "_run_gh", forbidden)
    registry = module.provision(dry_run=True)
    assert sorted(registry) == ["genesis-node-2", "genesis-node-3"]
    assert all(len(base64.b64decode(value, validate=True)) == 32 for value in registry.values())


def test_signing_material_is_sent_to_secret_command_over_stdin(monkeypatch) -> None:
    calls = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(args, *, stdin_text=None, check=True):
        calls.append((args, stdin_text))
        return Result()

    monkeypatch.setattr(module, "_run_gh", fake_run)
    identity = module.generate_identity("genesis-node-2", "Maxhm007/Genesis-Node-2")
    module.set_private_secret(identity)

    args, stdin_text = calls[0]
    assert args[:3] == ["secret", "set", module.SECRET_NAME]
    assert identity.private_pem not in " ".join(args)
    assert stdin_text == identity.private_pem

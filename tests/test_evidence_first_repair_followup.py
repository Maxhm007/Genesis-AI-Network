from __future__ import annotations

import json
import subprocess
from pathlib import Path

import genesis.github_issue_capability_builder as builder
from genesis.coding import CodingModule
from genesis.github_issue_capability_builder import EvidenceFirstRepairProvider, GitHubIssueLearnedCapabilityProvider
from scripts.github_issue_autorepair import allowed_issue_repair_paths


def _followup_issue(*, author: str = "github-actions[bot]", target: str = "genesis/alpha.py") -> dict:
    return {
        "number": 900,
        "title": "[Genesis Repair Follow-up] #899 — difficult capability repair",
        "user": {"login": author},
        "body": (
            "<!-- genesis-unsolved-successor-of:899 -->\n"
            "<!-- genesis-unsolved-root:899 -->\n"
            "- **Parent issue:** #899\n"
            "- **Task type:** `repair_followup`\n"
            f"- **Target:** `{target}`\n\n"
            "### Why the parent was not solved\n"
            "The bounded repair exhausted 3/3 attempts with retry_pending_capability and no promotable candidate.\n\n"
            "### Required next strategy\n"
            "Use a materially different bounded strategy.\n"
        ),
    }


def test_evidence_first_provider_preserves_delegate_contract_and_adds_read_only_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_alpha.py").write_text(
        "def test_alpha_value():\n"
        "    assert VALUE == 4\n",
        encoding="utf-8",
    )

    class RecordingDelegate:
        name = "recording-local-coder"

        def __init__(self) -> None:
            self.prompt = ""

        def available(self) -> bool:
            return True

        def reason(self, prompt: str) -> str:
            self.prompt = prompt
            return json.dumps(
                {
                    "edits": [
                        {
                            "path": "genesis/alpha.py",
                            "start_line": 1,
                            "end_line": 1,
                            "new": "VALUE = 4",
                        }
                    ]
                }
            )

    delegate = RecordingDelegate()
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://127.0.0.1:8766")
    monkeypatch.setattr(builder, "GenesisHTTPProvider", lambda *args, **kwargs: delegate)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _followup_issue(),
        CodingModule(tmp_path),
    )

    assert isinstance(provider, EvidenceFirstRepairProvider)
    raw = provider.reason(
        "ROLE: bounded_coding_engineer\nVALID_PATHS:\n[\"genesis/alpha.py\"]\nReturn JSON only."
    )
    assert json.loads(raw)["edits"][0]["path"] == "genesis/alpha.py"
    assert delegate.prompt.splitlines()[0] == "ROLE: bounded_coding_engineer"
    assert "ROLE: bounded_coding_engineer" in delegate.prompt.splitlines()[:8]
    assert "DIFFICULT_REPAIR_MODE" in delegate.prompt
    assert "retry_pending_capability" in delegate.prompt
    assert "test_alpha_value" in delegate.prompt
    assert "assert VALUE == 4" in delegate.prompt
    assert "does not expand VALID_PATHS" in delegate.prompt
    assert 'VALID_PATHS:\n["genesis/alpha.py"]' in delegate.prompt

    allowed = allowed_issue_repair_paths(["genesis/alpha.py"])
    assert allowed == {"genesis/alpha.py", "tests/test_alpha.py"}


def test_user_authored_followup_cannot_activate_evidence_first_route(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://127.0.0.1:8766")

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _followup_issue(author="Maxhm007"),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_followup_without_configured_local_provider_falls_back_safely(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.delenv("GENESIS_REPAIR_PROVIDER_URL", raising=False)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _followup_issue(),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_protected_followup_target_never_activates_evidence_first_route(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "security.py").write_text("SAFE = True\n", encoding="utf-8")
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://127.0.0.1:8766")

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _followup_issue(target="genesis/security.py"),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_recent_target_history_fails_closed_when_git_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(builder.subprocess, "run", unavailable)
    assert GitHubIssueLearnedCapabilityProvider._recent_target_history(tmp_path, "genesis/alpha.py") == ""


def test_recent_target_history_fails_closed_on_timeout(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "log"], timeout=3)

    monkeypatch.setattr(builder.subprocess, "run", timed_out)
    assert GitHubIssueLearnedCapabilityProvider._recent_target_history(tmp_path, "genesis/alpha.py") == ""


def test_followup_path_validation_error_falls_back_safely(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://127.0.0.1:8766")
    coding = CodingModule(tmp_path)

    def reject(_paths):
        raise RuntimeError("boundary rejected")

    monkeypatch.setattr(coding.executor, "_validate_paths", reject)
    provider = GitHubIssueLearnedCapabilityProvider.for_issue(tmp_path, _followup_issue(), coding)

    assert provider is None

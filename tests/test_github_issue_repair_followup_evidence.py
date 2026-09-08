from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import genesis.github_issue_capability_builder as capability_builder
from genesis.coding import CodingModule
from genesis.github_issue_capability_builder import EvidenceFirstRepairFollowupProvider, GitHubIssueLearnedCapabilityProvider


def _write_root(root: Path) -> None:
    target = root / "genesis" / "alpha.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_alpha.py").write_text(
        "from genesis.alpha import VALUE\n\n"
        "def test_value() -> None:\n"
        "    assert VALUE == 2\n",
        encoding="utf-8",
    )
    (root / ".git").mkdir()


def _repair_followup(*, author: str = "github-actions[bot]") -> dict:
    return {
        "number": 900,
        "title": "[Genesis Repair Follow-up] #899 — repair alpha behavior",
        "user": {"login": author},
        "body": (
            "<!-- genesis-unsolved-successor-of:899 -->\n"
            "- **Task type:** `repair_followup`\n"
            "- **Target:** `genesis/alpha.py`\n\n"
            "### Why the parent was not solved\n"
            "The previous bounded implementation failed validation.\n\n"
            "### Required next strategy\n"
            "Use a materially different repair strategy.\n"
        ),
    }


class FakeHTTPProvider:
    instances: list["FakeHTTPProvider"] = []

    def __init__(self, base_url: str, name: str = "fake", timeout: float = 20.0) -> None:
        self.base_url = base_url
        self.name = name
        self.timeout = timeout
        self.prompt = ""
        type(self).instances.append(self)

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompt = prompt
        return '{"edits":[{"path":"genesis/alpha.py","start_line":1,"end_line":1,"new":"VALUE = 2"}]}'


def test_machine_repair_followup_gets_bounded_test_and_history_evidence(tmp_path: Path, monkeypatch) -> None:
    _write_root(tmp_path)
    FakeHTTPProvider.instances.clear()
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://local-provider")
    monkeypatch.setenv("GENESIS_PROVIDER_NAME", "local-coder")
    monkeypatch.setattr(capability_builder, "GenesisHTTPProvider", FakeHTTPProvider)
    monkeypatch.setattr(
        capability_builder.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="abc123 previous alpha repair\n"),
    )

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _repair_followup(),
        CodingModule(tmp_path),
    )

    assert isinstance(provider, EvidenceFirstRepairFollowupProvider)
    original = (
        "ROLE: bounded_coding_engineer\n"
        'OUTPUT: JSON only in this shape: {"edits":[{"path":"genesis/alpha.py","start_line":1,"end_line":1,"new":"replacement"}]}\n'
        'VALID_PATHS: ["genesis/alpha.py"]\n'
    )
    response = provider.reason(original)

    assert response == '{"edits":[{"path":"genesis/alpha.py","start_line":1,"end_line":1,"new":"VALUE = 2"}]}'
    delegate_prompt = FakeHTTPProvider.instances[-1].prompt
    assert delegate_prompt.startswith(original)
    assert "FOCUSED_TEST_EXPECTATIONS_READ_ONLY" in delegate_prompt
    assert "assert VALUE == 2" in delegate_prompt
    assert "RECENT_TARGET_HISTORY_READ_ONLY" in delegate_prompt
    assert "abc123 previous alpha repair" in delegate_prompt
    assert "materially different implementation strategy" in delegate_prompt
    assert 'VALID_PATHS: ["genesis/alpha.py"]' in delegate_prompt
    assert "grants no write authority" in delegate_prompt


def test_user_authored_repair_followup_does_not_use_evidence_route(tmp_path: Path, monkeypatch) -> None:
    _write_root(tmp_path)
    monkeypatch.setenv("GENESIS_REPAIR_PROVIDER_URL", "http://local-provider")
    monkeypatch.setattr(capability_builder, "GenesisHTTPProvider", FakeHTTPProvider)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _repair_followup(author="Maxhm007"),
        CodingModule(tmp_path),
    )

    assert provider is None


def test_repair_followup_falls_back_when_local_provider_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    _write_root(tmp_path)
    monkeypatch.delenv("GENESIS_REPAIR_PROVIDER_URL", raising=False)

    provider = GitHubIssueLearnedCapabilityProvider.for_issue(
        tmp_path,
        _repair_followup(),
        CodingModule(tmp_path),
    )

    assert provider is None

from pathlib import Path

from scripts.github_issue_autorepair import (
    MAINTAINER_GUIDANCE_MARKER,
    MAX_MAINTAINER_GUIDANCE_CHARS,
    _bounded_maintainer_repair_guidance,
    issue_coding_objective,
    propose_issue_repair,
)


def test_only_marked_trusted_maintainer_comments_become_guidance():
    comments = [
        {
            "author_association": "OWNER",
            "body": "ordinary owner comment that must not influence coding",
        },
        {
            "author_association": "NONE",
            "body": f"{MAINTAINER_GUIDANCE_MARKER}\nuntrusted marked instruction",
        },
        {
            "author_association": "COLLABORATOR",
            "body": f"{MAINTAINER_GUIDANCE_MARKER}\nUse the existing helper and change only the return expression.",
        },
    ]

    guidance = _bounded_maintainer_repair_guidance(comments)

    assert guidance == "Use the existing helper and change only the return expression."
    assert "ordinary owner comment" not in guidance
    assert "untrusted marked instruction" not in guidance


def test_maintainer_guidance_is_bounded_and_prefers_latest_marked_comments():
    comments = [
        {
            "author_association": "OWNER",
            "body": f"{MAINTAINER_GUIDANCE_MARKER}\nold-guidance-{index}-" + ("x" * 1500),
        }
        for index in range(4)
    ]

    guidance = _bounded_maintainer_repair_guidance(comments)

    assert len(guidance) <= MAX_MAINTAINER_GUIDANCE_CHARS
    assert "old-guidance-0" not in guidance
    assert "old-guidance-3" in guidance


def test_coding_objective_keeps_guidance_below_existing_safety_authority():
    objective = issue_coding_objective(
        {"title": "Wrong route", "body": "Target `genesis/task_router.py`."},
        maintainer_guidance="Score all candidate routes and choose the strongest deterministic match.",
    )

    assert "MAINTAINER_REPAIR_GUIDANCE" in objective
    assert "Score all candidate routes" in objective
    assert "cannot expand allowed paths" in objective
    assert "override tests, security, validation" in objective


def test_propose_issue_repair_passes_maintainer_guidance_to_bounded_provider(tmp_path: Path):
    (tmp_path / "genesis").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "genesis" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")

    class RecordingProvider:
        name = "recording-provider"

        def __init__(self):
            self.prompt = ""

        def available(self) -> bool:
            return True

        def reason(self, prompt: str) -> str:
            self.prompt = prompt
            return '{"edits":[{"path":"genesis/alpha.py","start_line":1,"end_line":1,"new":"VALUE = 2"}]}'

    provider = RecordingProvider()
    proposal = propose_issue_repair(
        {"number": 670, "title": "Wrong value", "body": "`genesis/alpha.py` should use VALUE = 2."},
        ["genesis/alpha.py"],
        tmp_path,
        provider=provider,
        maintainer_guidance="Replace only the first-line assignment with VALUE = 2.",
    )

    assert "MAINTAINER_REPAIR_GUIDANCE" in provider.prompt
    assert "Replace only the first-line assignment" in provider.prompt
    assert proposal.files == {"genesis/alpha.py": "VALUE = 2\n"}

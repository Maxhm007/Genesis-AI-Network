from __future__ import annotations

import json
from pathlib import Path

from genesis.coding import CodingModule


class SequencedProvider:
    name = "sequenced-provider"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    def reason(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def test_provider_cannot_edit_path_outside_current_numbered_context(tmp_path: Path) -> None:
    genesis = tmp_path / "genesis"
    genesis.mkdir()
    (genesis / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (genesis / "agentic.py").write_text("VALUE = 1\n", encoding="utf-8")

    provider = SequencedProvider(
        [
            json.dumps(
                {
                    "edits": [
                        {
                            "path": "genesis/agentic.py",
                            "start_line": 1,
                            "end_line": 1,
                            "new": "VALUE = 3",
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "edits": [
                        {
                            "path": "genesis/alpha.py",
                            "start_line": 1,
                            "end_line": 1,
                            "new": "VALUE = 2",
                        }
                    ]
                }
            ),
        ]
    )

    proposal = CodingModule(tmp_path).propose(
        "Set alpha VALUE to 2.",
        ["genesis/alpha.py"],
        provider=provider,
    )

    assert proposal.files == {"genesis/alpha.py": "VALUE = 2\n"}
    assert len(provider.prompts) == 2
    assert "coding proposal path must match VALID_PATHS exactly" in provider.prompts[1]
    assert 'VALID_PATHS: ["genesis/alpha.py"]' in provider.prompts[1]

import json

import pytest

from genesis.coding import CodingModule


def test_syntax_retry_shows_rejected_expression_and_preserves_original_coordinates(tmp_path):
    target = tmp_path / "genesis" / "sample.py"
    target.parent.mkdir()
    target.write_text('VALUES = [\n    "a",\n    "b",\n]\n')
    module = CodingModule(tmp_path)

    class Provider:
        name = "test"
        prompts = []

        def reason(self, prompt):
            self.prompts.append(prompt)
            replacement = 'return "c"' if len(self.prompts) == 1 else '"c",'
            return json.dumps({"edits": [{"path": "genesis/sample.py", "start_line": 2,
                                         "end_line": 2, "new": replacement}]})

    provider = Provider()
    proposal = module.propose("Update VALUES", ["genesis/sample.py"], provider=provider)
    assert len(provider.prompts) == 2
    assert "REJECTED_CANDIDATE_CONTEXT" in provider.prompts[1]
    assert '2|    return "c"' in provider.prompts[1]
    assert "original NUMBERED_CONTEXT coordinates" in provider.prompts[1]
    assert proposal.files["genesis/sample.py"] == 'VALUES = [\n    "c",\n    "b",\n]\n'
    assert target.read_text() == 'VALUES = [\n    "a",\n    "b",\n]\n'


def test_invalid_candidate_still_rejected_with_bounded_feedback(tmp_path):
    module = CodingModule(tmp_path)
    source = "# " + "x" * 10000 + "\nVALUE = (\nreturn 1\n)\n"
    with pytest.raises(ValueError) as raised:
        module.validate_proposal({"files": {"genesis/sample.py": source}}, "test")
    assert "invalid Python syntax" in str(raised.value)
    assert len(str(raised.value)) < 3000


def test_placeholder_edit_is_rejected_and_retried_with_real_code(tmp_path):
    target = tmp_path / "genesis" / "sample.py"
    target.parent.mkdir()
    target.write_text("VALUE = 1\n")
    module = CodingModule(tmp_path)

    class Provider:
        name = "test"

        def __init__(self):
            self.prompts = []

        def reason(self, prompt):
            self.prompts.append(prompt)
            replacement = "replacement text" if len(self.prompts) == 1 else "VALUE = 2"
            return json.dumps({"edits": [{"path": "genesis/sample.py", "start_line": 1,
                                         "end_line": 1, "new": replacement}]})

    provider = Provider()
    proposal = module.propose("Change VALUE to 2", ["genesis/sample.py"], provider=provider)

    assert len(provider.prompts) == 2
    assert "not placeholder text" in provider.prompts[1]
    assert '"new":"replacement text"' not in provider.prompts[0]
    assert '"new":"replacement text"' not in provider.prompts[1]
    assert proposal.files["genesis/sample.py"] == "VALUE = 2\n"

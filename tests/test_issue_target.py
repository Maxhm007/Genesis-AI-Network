from genesis.issue_target import extract_issue_target


def test_extracts_structured_markdown_target():
    body = "- **Target:** `genesis/memory.py`\n"
    assert extract_issue_target(body) == "genesis/memory.py"


def test_extracts_genesis_discovery_target():
    body = "Genesis independently discovered this issue.\n\nTarget: `genesis/memory.py`\n"
    assert extract_issue_target(body) == "genesis/memory.py"


def test_normalizes_backslashes():
    body = "Target: `genesis\\memory.py`\n"
    assert extract_issue_target(body) == "genesis/memory.py"


def test_does_not_infer_target_from_arbitrary_inline_path():
    body = "Observed problem mentions `genesis/memory.py` but has no explicit target field."
    assert extract_issue_target(body) == ""

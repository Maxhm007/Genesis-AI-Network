import pytest

from genesis.learned_capability_acceptance import (
    requires_new_registration,
    top_level_registration_names,
    validate_learned_capability_candidate,
)


ISSUE_BODY = "Acceptance: The learned-capability module adds one registered executable capability."
BASE = """
def old_handler():
    return 1

register_capability('old', 'desc', 'evidence', old_handler)
"""


def test_issue_427_style_nonsemantic_patch_is_rejected():
    candidate = BASE.replace("return 1", "import torch\n    return 1")
    with pytest.raises(ValueError, match="adds no new top-level register_capability"):
        validate_learned_capability_candidate(
            issue_body=ISSUE_BODY,
            target="genesis/learned_capabilities.py",
            base_source=BASE,
            candidate_source=candidate,
        )


def test_real_new_top_level_registration_is_accepted():
    candidate = BASE + """
def new_handler():
    return 2

register_capability('new', 'desc', 'evidence', new_handler)
"""
    result = validate_learned_capability_candidate(
        issue_body=ISSUE_BODY,
        target="genesis/learned_capabilities.py",
        base_source=BASE,
        candidate_source=candidate,
    )
    assert result["ok"] is True
    assert result["added_registrations"] == ["new"]


def test_comments_strings_and_nested_calls_do_not_count():
    candidate = BASE + """
TEXT = "register_capability('fake', 'd', 'e', handler)"
# register_capability('comment', 'd', 'e', handler)
def later():
    register_capability('nested', 'd', 'e', later)
"""
    assert top_level_registration_names(candidate) == {"old"}
    with pytest.raises(ValueError):
        validate_learned_capability_candidate(
            issue_body=ISSUE_BODY,
            target="genesis/learned_capabilities.py",
            base_source=BASE,
            candidate_source=candidate,
        )


def test_gate_only_applies_to_explicit_learned_capability_requirement():
    assert requires_new_registration(ISSUE_BODY, "genesis/learned_capabilities.py") is True
    assert requires_new_registration("Fix a bug.", "genesis/learned_capabilities.py") is False
    assert requires_new_registration(ISSUE_BODY, "genesis/coding.py") is False

from __future__ import annotations

from genesis.review_materiality import evaluate_python_materiality


def test_rejects_duplicate_return_that_replaces_docstring() -> None:
    base = '''def check(lines):
    """Comments and whitespace cannot satisfy a required Python suite body."""
    return any(line.strip() for line in lines)
'''
    candidate = '''def check(lines):
    return any(line.strip() for line in lines)
    return any(line.strip() for line in lines)
'''

    ok, feedback = evaluate_python_materiality(
        base,
        candidate,
        require_behavior_change=True,
    )

    assert ok is False
    assert feedback == "materiality_gate:introduced_adjacent_duplicate_statement"


def test_rejects_new_unreachable_statement() -> None:
    base = '''def value(flag):
    if flag:
        return 1
    return 2
'''
    candidate = '''def value(flag):
    if flag:
        return 1
    return 2
    marker = "never reached"
'''

    ok, feedback = evaluate_python_materiality(
        base,
        candidate,
        require_behavior_change=False,
    )

    assert ok is False
    assert feedback == "materiality_gate:introduced_unreachable_statement"


def test_capability_growth_rejects_docstring_only_change() -> None:
    base = '''def value():
    """Old explanation."""
    return 1
'''
    candidate = '''def value():
    """New explanation."""
    return 1
'''

    ok, feedback = evaluate_python_materiality(
        base,
        candidate,
        require_behavior_change=True,
    )

    assert ok is False
    assert feedback == "materiality_gate:no_reachable_behavior_change"


def test_real_reachable_behavior_change_passes() -> None:
    base = '''def check(lines):
    return any(line.strip() for line in lines)
'''
    candidate = '''def check(lines):
    return all(line.strip() for line in lines)
'''

    ok, feedback = evaluate_python_materiality(
        base,
        candidate,
        require_behavior_change=True,
    )

    assert ok is True
    assert feedback == "materiality_gate:pass"


def test_preexisting_duplicate_does_not_block_unrelated_real_change() -> None:
    base = '''def legacy():
    ping()
    ping()

def value():
    return 1
'''
    candidate = '''def legacy():
    ping()
    ping()

def value():
    return 2
'''

    ok, feedback = evaluate_python_materiality(
        base,
        candidate,
        require_behavior_change=True,
    )

    assert ok is True
    assert feedback == "materiality_gate:pass"

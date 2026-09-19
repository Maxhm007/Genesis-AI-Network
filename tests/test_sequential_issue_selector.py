from datetime import datetime, timezone

from scripts.sequential_issue_selector import candidate, select


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def issue(number, title, body, labels=(), created_at='2026-09-19T00:00:00Z'):
    return {
        'number': number,
        'title': title,
        'body': body,
        'created_at': created_at,
        'labels': [{'name': x} for x in labels],
    }


def test_urgent_action_failure_gets_lane_bonus():
    urgent = issue(10, 'Genesis Action failure: workflow failed', 'Workflow failed', labels=('genesis-action-failure',))
    general = issue(11, 'General repair', 'Target exactly genesis/memory.py')
    ranked = select([general, urgent], now=NOW)['ranked']
    assert ranked[0]['number'] == 10
    assert ranked[0]['kind'] == 'urgent'
    assert ranked[0]['lane_bonus'] == 25.0


def test_high_value_newer_issue_can_beat_older_fifo_issue():
    older = issue(20, 'General repair', 'Target exactly genesis/memory.py', created_at='2026-09-01T00:00:00Z')
    newer = issue(21, '[Genesis Repair] critical blocker', 'Target exactly genesis/memory.py\nBlocks #30\nBlocks #31\nBlocks #32\nBlocks #33', labels=('severity-high', 'owner-priority', 'genesis-repair'), created_at='2026-09-18T00:00:00Z')
    selected = select([older, newer], now=NOW)['selected']
    assert selected['number'] == 21
    assert selected['score'] > candidate(older, now=NOW)['score']


def test_stuck_issue_gets_retry_penalty():
    clean = issue(30, 'General repair', 'Target exactly genesis/memory.py')
    stuck = issue(31, 'General repair', 'Target exactly genesis/memory.py', labels=('genesis-stuck-10x',))
    assert candidate(clean, now=NOW)['score'] > candidate(stuck, now=NOW)['score']


def test_verified_or_blocked_issues_are_excluded():
    verified = issue(40, 'General repair', 'Target exactly genesis/memory.py', labels=('genesis-verified',))
    blocked = issue(41, 'General repair', 'Target exactly genesis/memory.py', labels=('genesis-blocked',))
    assert candidate(verified, now=NOW) is None
    assert candidate(blocked, now=NOW) is None


def test_selector_is_explainable():
    row = candidate(issue(50, '[Genesis Repair] reliability issue', 'Target exactly genesis/memory.py\nUnlocks #60', labels=('genesis-repair',)), now=NOW)
    assert row is not None
    assert row['kind'] == 'repair'
    assert 'breakdown' in row
    assert row['base_score'] >= 0

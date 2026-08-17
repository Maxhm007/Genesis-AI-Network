from genesis.health import build_health_snapshot

def test_health_snapshot():
    result = build_health_snapshot(node='test')
    assert result['status'] == 'ok'
    assert result['details']['node'] == 'test'
    assert result['created_at']

def test_health_snapshot_accepts_explicit_status():
    result = build_health_snapshot(status='degraded', node='autonomy-trial')
    assert result['status'] == 'degraded'
    assert result['details']['node'] == 'autonomy-trial'
    assert 'status' not in result['details']

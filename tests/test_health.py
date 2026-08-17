from genesis.health import build_health_snapshot

def test_health_snapshot():
    result = build_health_snapshot(node='test')
    assert result['status'] == 'ok'
    assert result['details']['node'] == 'test'
    assert result['created_at']
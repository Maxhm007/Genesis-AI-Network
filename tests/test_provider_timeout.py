from genesis.providers import MAX_PROVIDER_TIMEOUT_SECONDS, _bounded_timeout


def test_long_local_reasoning_timeout_is_honored_within_bound():
    assert _bounded_timeout("240") == 240.0
    assert _bounded_timeout("999") == MAX_PROVIDER_TIMEOUT_SECONDS
    assert _bounded_timeout("1") == 5.0

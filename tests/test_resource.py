import pytest

from genesis.resource import ResourceModule


def test_snapshot_preserves_boolean_network_availability():
    module = ResourceModule()

    assert module.snapshot(10, 20, 30, network_available=True).network_available is True
    assert module.snapshot(10, 20, 30, network_available=False).network_available is False


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_snapshot_rejects_non_boolean_network_availability(value):
    module = ResourceModule()

    with pytest.raises((TypeError, ValueError)):
        module.snapshot(10, 20, 30, network_available=value)


def test_resource_normalization_and_capacity_score_remain_unchanged():
    module = ResourceModule()
    snapshot = module.snapshot(-5, 120, 25, battery_percent=10, network_available=True)

    assert snapshot.cpu_percent == 0.0
    assert snapshot.memory_percent == 100.0
    assert snapshot.disk_percent == 25.0
    assert snapshot.battery_percent == 10.0
    assert module.capacity_score(snapshot) == 33.0

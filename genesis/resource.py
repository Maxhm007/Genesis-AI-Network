from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    battery_percent: float | None = None
    network_available: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


class ResourceModule:
    """Normalize resource telemetry for routing and scheduling decisions."""

    @staticmethod
    def _pct(value: float) -> float:
        return max(0.0, min(100.0, float(value)))

    def snapshot(self, cpu_percent: float, memory_percent: float, disk_percent: float,
                 battery_percent: float | None = None, network_available: bool = True) -> ResourceSnapshot:
        if not isinstance(network_available, bool):
            raise TypeError("network_available must be a boolean")
        battery = None if battery_percent is None else self._pct(battery_percent)
        return ResourceSnapshot(
            self._pct(cpu_percent),
            self._pct(memory_percent),
            self._pct(disk_percent),
            battery,
            network_available,
        )

    def capacity_score(self, snapshot: ResourceSnapshot) -> float:
        free_cpu = 100.0 - snapshot.cpu_percent
        free_memory = 100.0 - snapshot.memory_percent
        free_disk = 100.0 - snapshot.disk_percent
        score = (free_cpu * 0.4) + (free_memory * 0.4) + (free_disk * 0.2)
        if snapshot.battery_percent is not None and snapshot.battery_percent < 20:
            score *= 0.6
        if not snapshot.network_available:
            score *= 0.8
        return round(max(0.0, min(100.0, score)), 2)

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidatorSpec:
    validator_id: str
    port: int
    key_path: str
    enabled: bool = True


class ValidatorFleet:
    """Supervise any number of local validator service processes.

    This is a process supervisor, not a claim of host independence. For true
    validator independence, different ValidatorSpecs should run on different
    machines/operators. The same configuration format works on every host.
    """

    def __init__(self, root: Path, specs: list[ValidatorSpec], restart_delay: float = 2.0) -> None:
        self.root = root.resolve()
        self.specs = [spec for spec in specs if spec.enabled]
        self.restart_delay = restart_delay
        self.processes: dict[str, subprocess.Popen] = {}
        self.stopping = False

    @classmethod
    def from_config(cls, root: Path, config_path: Path | None = None) -> "ValidatorFleet":
        root = root.resolve()
        path = config_path or (root / "config" / "validators.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        specs = [ValidatorSpec(**item) for item in data.get("validators", [])]
        if not specs:
            raise RuntimeError("validator fleet has no configured validators")
        return cls(root, specs, restart_delay=float(data.get("restart_delay_seconds", 2.0)))

    def _command(self, spec: ValidatorSpec) -> list[str]:
        return [
            sys.executable,
            "-m",
            "genesis.validator_service",
            "--validator-id",
            spec.validator_id,
            "--key-path",
            str(self.root / spec.key_path),
            "--port",
            str(spec.port),
        ]

    def start_validator(self, spec: ValidatorSpec) -> None:
        current = self.processes.get(spec.validator_id)
        if current and current.poll() is None:
            return
        self.processes[spec.validator_id] = subprocess.Popen(
            self._command(spec),
            cwd=self.root,
            stdout=None,
            stderr=None,
        )

    def start_all(self) -> None:
        ids = [spec.validator_id for spec in self.specs]
        if len(ids) != len(set(ids)):
            raise RuntimeError("validator IDs must be unique")
        ports = [spec.port for spec in self.specs]
        if len(ports) != len(set(ports)):
            raise RuntimeError("validator ports must be unique on one host")
        for spec in self.specs:
            self.start_validator(spec)

    def supervise_once(self) -> list[str]:
        restarted: list[str] = []
        for spec in self.specs:
            process = self.processes.get(spec.validator_id)
            if process is None or process.poll() is not None:
                if self.stopping:
                    continue
                time.sleep(self.restart_delay)
                self.start_validator(spec)
                restarted.append(spec.validator_id)
        return restarted

    def run_forever(self, poll_seconds: float = 2.0) -> None:
        self.start_all()

        def stop(*_args):
            self.stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            while not self.stopping:
                self.supervise_once()
                time.sleep(poll_seconds)
        finally:
            for process in self.processes.values():
                if process.poll() is None:
                    process.terminate()
            for process in self.processes.values():
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ValidatorFleet.from_config(root).run_forever()


if __name__ == "__main__":
    main()

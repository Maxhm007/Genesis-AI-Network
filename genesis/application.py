from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .modules.task_queue import PersistentTaskQueue


@dataclass(frozen=True)
class ApplicationTarget:
    target_id: str
    platform: str
    source_root: str
    artifact: str
    architecture: str
    priority: int
    enabled: bool = True


class ApplicationModule:
    """Own Genesis application surfaces without owning release authority.

    The module turns explicitly configured desktop/mobile product gaps into
    persistent engineering tasks. Coding may modify application source through
    the normal bounded candidate flow, but this module cannot alter GitHub
    workflows, signing credentials, validator rules, or promote/release output.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.queue = PersistentTaskQueue(self.root / "runtime" / "genesis_tasks.sqlite3")

    def _config_targets(self) -> tuple[ApplicationTarget, ...]:
        path = self.root / "config" / "applications.json"
        if not path.exists():
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        targets = payload.get("targets", [])
        if not isinstance(targets, list):
            raise ValueError("application target config must contain a targets list")
        return tuple(ApplicationTarget(**item) for item in targets)

    def targets(self) -> tuple[ApplicationTarget, ...]:
        return tuple(target for target in self._config_targets() if target.enabled)

    def inspect(self) -> dict:
        results = []
        for target in self.targets():
            source = self.root / target.source_root
            present = source.exists()
            results.append({**asdict(target), "source_present": present, "status": "present" if present else "missing"})
        return {"module": "genesis.application", "targets": results}

    @staticmethod
    def _objective(target: ApplicationTarget, present: bool) -> str:
        if target.target_id == "windows-desktop":
            if not present:
                return (
                    "Build the Genesis AI Windows desktop application under desktop/. Use the existing Genesis Core API, "
                    "provide Chat, Memory, Coding, Security, Research, Network and Updates surfaces, and keep the UI lightweight. "
                    "Do not modify CI workflows, signing policy, Constitution, Genesis Block, or validation rules."
                )
            if not present:
                return (
                    "Build the Genesis AI Windows desktop application under desktop/. Use the existing Genesis Core API, "
                    "provide Chat, Memory, Coding, Security, Research, Network and Updates surfaces, and keep the UI lightweight. "
                    "Do not modify CI workflows, signing policy, Constitution, Genesis Block, or validation rules."
                )
            else:
                return (
                    "Improve the Genesis Windows desktop application with the smallest useful, tested, accessible change. Prioritize runtime health, real module/status data, update UX, and resource efficiency. Do not modify CI workflows."
                )
        if target.target_id == "android-mobile":
            if not present:
                return (
                    "Bootstrap a minimal Genesis Android mobile application under mobile/ that can build into an APK. "
                    "Use a lightweight client architecture connected to an explicitly configured authenticated Genesis API; "
                    "never embed credentials. Include Chat, status and Settings first. Keep local-core-on-Android as a future option. "
                    "Do not modify CI workflows, signing policy, Constitution, Genesis Block, or validation rules."
                )
            return (
                "Improve the Genesis Android application with the smallest useful tested change. Prioritize secure API configuration, "
                "Chat, Memory/status visibility, efficient networking and offline-safe UI. Never embed tokens or weaken transport/authentication."
            )
        return f"Improve the Genesis application target {target.target_id} safely and minimally."

    def ensure_development_tasks(self) -> list[dict]:
        created = []
        for target in self.targets():
            present = (self.root / target.source_root).exists()
            phase = "improve" if present else "bootstrap"
            key = f"application:{target.target_id}:{phase}:v1"
            context_paths = []
            if target.target_id == "windows-desktop" and present:
                context_paths = [
                    "desktop/ui/index.html",
                    "desktop/src-tauri/tauri.conf.json",
                    "desktop/src-tauri/src/main.rs",
                    "genesis/communication_server.py",
                ]
            task, was_created = self.queue.create_unique(
                key,
                self._objective(target, present),
                module_id="genesis.application",
                priority=target.priority if not present else max(70, target.priority - 18),
                payload={
                    "task_type": "application_development",
                    "target": asdict(target),
                    "phase": phase,
                    "context_paths": context_paths,
                    "release_authority": False,
                    "required_validation": "security + independent validator quorum",
                },
            )
            created.append(
                {
                    "target_id": target.target_id,
                    "task_id": task.task_id,
                    "created": was_created,
                    "phase": phase,
                    "priority": task.priority,
                }
            )
        return created

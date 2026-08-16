from pathlib import Path

from genesis.application import ApplicationModule
from genesis.modules.registry import ModuleRegistry
from genesis.selfdev import normalize_selfdev_path


def test_application_module_registers(tmp_path: Path):
    (tmp_path / "config" / "modules.d").mkdir(parents=True)
    (tmp_path / "config" / "modules.d" / "application.json").write_text(
        '{"modules":[{"module_id":"genesis.application","name":"Application Module","version":"0.1.0","purpose":"apps","capabilities":["desktop_application_development"],"permissions":[],"dependencies":[],"status":"active","dynamic":false,"mutable":true,"protected":false,"implementation":"genesis.application","metadata":{}}]}',
        encoding="utf-8",
    )
    registry = ModuleRegistry.from_default_config(tmp_path)
    assert registry.get("genesis.application") is not None


def test_application_tasks_cover_desktop_and_android(tmp_path: Path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "desktop").mkdir()
    module = ApplicationModule(tmp_path)
    tasks = module.ensure_development_tasks()
    by_target = {item["target_id"]: item for item in tasks}
    assert by_target["windows-desktop"]["phase"] == "improve"
    assert by_target["android-mobile"]["phase"] == "bootstrap"
    queued = module.queue.list(limit=10)
    assert {task.module_id for task in queued} == {"genesis.application"}


def test_application_source_is_inside_bounded_selfdev_sandbox(tmp_path: Path):
    assert normalize_selfdev_path(tmp_path, "desktop/ui/index.html") == "desktop/ui/index.html"
    assert normalize_selfdev_path(tmp_path, "mobile/src/index.html") == "mobile/src/index.html"


def test_application_module_cannot_change_release_workflows(tmp_path: Path):
    try:
        normalize_selfdev_path(tmp_path, ".github/workflows/desktop-windows-release.yml")
    except RuntimeError as exc:
        assert "workflow" in str(exc).lower()
    else:
        raise AssertionError("Application development must not gain workflow write access")

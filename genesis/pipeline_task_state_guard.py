from __future__ import annotations

from .autonomy_pipeline import PipelineStore
from .modules.task_queue import PersistentTaskQueue


PATCH_VERSION = "genesis-pipeline-task-state-guard-v1"
NON_RUNNABLE_STATES = {"paused", "complete", "quarantined", "cancelled"}


def install_pipeline_task_state_guard() -> None:
    """Keep pipeline activity aligned with the authoritative task queue state.

    Pipeline metadata may retain a non-terminal specialist stage while the shared
    task queue deliberately pauses the task for an external dependency. Such work
    must remain durable, but it must not block unrelated runnable work. Once the
    task is resumed in the queue it automatically becomes visible to the pipeline
    again.
    """

    if getattr(PipelineStore, "_genesis_task_state_guard", None) == PATCH_VERSION:
        return

    original_list_active = PipelineStore.list_active

    def list_active(self: PipelineStore):
        records = original_list_active(self)
        queue = PersistentTaskQueue(self.path)
        runnable = []
        for record in records:
            task = queue.get(record.task_id)
            if task is None:
                continue
            if task.state in NON_RUNNABLE_STATES:
                continue
            runnable.append(record)
        return runnable

    PipelineStore.list_active = list_active
    PipelineStore._genesis_task_state_guard = PATCH_VERSION

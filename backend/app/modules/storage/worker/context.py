from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.tasks.events import publish_storage_sub_log_appended, publish_storage_sub_updated
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.timeline import STEP_LABELS


@dataclass
class StorageWorkerContext:
    db: Session
    main_task: StorageMainTask
    subtask: StorageSubTask
    config: dict
    provider: object
    owner_id: str

    def set_step(self, step: str) -> None:
        self.subtask.step = step
        self.db.flush()
        publish_storage_sub_updated(self.owner_id, self.subtask)
        self.log(
            "INFO",
            f"执行步骤: {step}",
            {"step": step},
            step=step,
            event="step_started",
        )

    def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
        *,
        step: str | None = None,
        event: str | None = None,
    ) -> dict:
        current_step = step or self.subtask.step
        entry = write_storage_subtask_log(
            str(self.subtask.id),
            level,
            message,
            context or {},
            step=current_step,
            step_label=STEP_LABELS.get(current_step),
            event=event,
        )
        publish_storage_sub_log_appended(self.owner_id, str(self.subtask.id), entry)
        return entry

    def publish_subtask(self) -> None:
        self.db.flush()
        publish_storage_sub_updated(self.owner_id, self.subtask)

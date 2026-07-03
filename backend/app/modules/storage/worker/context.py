from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask


@dataclass
class StorageWorkerContext:
    db: Session
    main_task: StorageMainTask
    subtask: StorageSubTask
    config: dict
    provider: object

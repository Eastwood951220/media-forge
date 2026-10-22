from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTaskItem
from backend.app.modules.scraping.tasks.events import (
    publish_scraping_item_log_appended,
    publish_scraping_item_updated,
)
from backend.app.modules.scraping.tasks.logs import write_scraping_item_log


def append_item_log(item: ScrapingTaskItem, level: str, message: str) -> None:
    entry = write_scraping_item_log(str(item.id), level, message, step=item.step or None)
    publish_scraping_item_log_appended(str(item.task.created_by), str(item.id), entry)


def start_item_step(db: Session, item: ScrapingTaskItem, step: str, message: str) -> None:
    item.step = step
    db.commit()
    publish_scraping_item_updated(str(item.task.created_by), item)
    append_item_log(item, "INFO", message)

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.models.scraping_task import ScrapingTaskItem
from backend.app.modules.scraping.tasks.events import (
    publish_scraping_item_log_appended,
    publish_scraping_item_updated,
)
from backend.app.modules.scraping.tasks.logs import write_scraping_item_log

logger = logging.getLogger(__name__)


def append_item_log(item: ScrapingTaskItem, owner_id: str, level: str, message: str) -> None:
    try:
        entry = write_scraping_item_log(str(item.id), level, message, step=item.step or None)
    except OSError:
        logger.warning("Could not save scraping item log: item=%s", item.id, exc_info=True)
        return
    publish_scraping_item_log_appended(owner_id, str(item.id), entry)


def start_item_step(db: Session, item: ScrapingTaskItem, owner_id: str, step: str, message: str) -> None:
    item.step = step
    db.commit()
    publish_scraping_item_updated(owner_id, item)
    append_item_log(item, owner_id, "INFO", message)

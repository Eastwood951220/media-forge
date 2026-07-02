"""Domain enums for crawler and media modules."""

from enum import StrEnum


class TaskStatus(StrEnum):
    """Crawl task lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class CrawlRunStatus(StrEnum):
    """Crawl run outcome status."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class MediaItemStatus(StrEnum):
    """Media item processing status."""

    PENDING = "pending"
    FETCHING = "fetching"
    FETCHED = "fetched"
    FAILED = "failed"
    SKIPPED = "skipped"

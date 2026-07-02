from enum import StrEnum


class CrawlRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class CrawlMode(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"


class DetailTaskStatus(StrEnum):
    PENDING_CRAWL = "pending_crawl"
    CRAWLED = "crawled"
    CRAWL_FAILED = "crawl_failed"
    SAVED = "saved"
    SAVE_FAILED = "save_failed"
    SKIPPED = "skipped"

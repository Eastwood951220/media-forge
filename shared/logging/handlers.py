"""Python logging handler for JSONL output."""

import logging

from shared.logging.jsonl import append_jsonl_log, build_log_entry


class JSONLHandler(logging.Handler):
    """A logging.Handler that writes structured JSONL log entries to a file."""

    def __init__(self, log_dir: str, filename: str, component: str = "backend") -> None:
        super().__init__()
        self.log_dir = log_dir
        self.filename = filename
        self.component = component

    def emit(self, record: logging.LogRecord) -> None:
        entry = build_log_entry(
            level=record.levelname,
            component=self.component,
            event=record.msg,
            message=record.getMessage(),
            logger=record.name,
            exc_info=self.format(record) if record.exc_info else None,
        )
        try:
            append_jsonl_log(self.log_dir, self.filename, entry)
        except Exception:
            self.handleError(record)

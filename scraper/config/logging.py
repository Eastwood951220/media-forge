import logging
from pathlib import Path

from scraper.config.settings import LOG_DIR
from shared.logging.handlers import JSONLHandler

LOG_DIR = Path(LOG_DIR)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """Return a scraper logger with JSONL and console handlers."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # JSONL handler for structured logging
        jsonl_handler = JSONLHandler(
            log_dir=str(LOG_DIR),
            filename="scraper.jsonl",
            component="scraper",
        )
        logger.addHandler(jsonl_handler)

        # Console handler for Docker stdout
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(LOG_FORMATTER)
        logger.addHandler(console_handler)

    return logger

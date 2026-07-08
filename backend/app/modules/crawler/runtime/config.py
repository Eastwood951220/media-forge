from __future__ import annotations

from pathlib import Path

from backend.app.modules.crawler.config.conf_reader import read_crawler_runtime_config


def read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int:
    return read_crawler_runtime_config(base_dir).INCREMENTAL_EXIST_THRESHOLD

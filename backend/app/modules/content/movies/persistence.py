from __future__ import annotations

from backend.app.modules.content.movies.filter_sync import sync_movie_filters
from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
from backend.app.modules.content.movies.magnet_persistence import (
    auto_select_best_magnet,
    normalize_magnet,
    upsert_magnets,
    upsert_movie_with_magnets,
)
from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, has_chinese_sub, parse_size_mb
from backend.app.modules.content.movies.movie_persistence import append_source_task_id, append_source_task_ids_for_codes, upsert_movie

__all__ = [
    "append_source_task_id",
    "append_source_task_ids_for_codes",
    "auto_select_best_magnet",
    "build_magnet_dedupe_key",
    "compute_magnet_weight",
    "extract_info_hash",
    "has_chinese_sub",
    "normalize_magnet",
    "parse_size_mb",
    "sync_movie_filters",
    "upsert_magnets",
    "upsert_movie",
    "upsert_movie_with_magnets",
]

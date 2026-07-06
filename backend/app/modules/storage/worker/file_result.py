from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScopedSearchResult:
    accepted_files: list[dict]
    log_context: dict

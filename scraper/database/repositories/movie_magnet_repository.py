from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import MovieMagnet
from shared.database.session import get_session_factory
from scraper.config.logging import get_logger


def extract_info_hash(magnet_url: str | None) -> str:
    if not magnet_url:
        return ""

    query = parse_qs(urlparse(magnet_url).query)
    for xt in query.get("xt", []):
        prefix = "urn:btih:"
        if xt.lower().startswith(prefix):
            return xt[len(prefix):].lower()
    return ""


def build_magnet_dedupe_key(movie_id: str, magnet: dict[str, Any]) -> str:
    info_hash = str(magnet.get("info_hash") or "").strip().lower()
    if not info_hash:
        info_hash = extract_info_hash(magnet.get("magnet") or magnet.get("magnet_url"))
    if info_hash:
        return info_hash

    parts = [
        str(movie_id),
        str(magnet.get("name") or ""),
        str(magnet.get("size_text") or ""),
        str(magnet.get("file_count") or ""),
        str(magnet.get("file_text") or ""),
        str(magnet.get("date") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _parse_size_mb(value) -> float:
    """Parse a size value (float, int, or string like '8.75GB') into MB."""
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return 0.0
    size_str = str(value).strip().upper()
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB)?", size_str)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "MB"
    multipliers = {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1024 * 1024}
    return number * multipliers.get(unit, 1)


def _has_chinese_sub(magnet: dict) -> bool:
    """Check if a magnet has Chinese subtitles via field, tags, or title keywords."""
    if magnet.get("has_chinese_sub"):
        return True
    tags = magnet.get("tags") or []
    if any("字幕" in str(tag) or "中字" in str(tag) for tag in tags):
        return True
    title = (magnet.get("title") or magnet.get("name") or "").lower()
    return any(kw in title for kw in ["chs", "cht", "chinese", "中字", "中文", "字幕"])


def compute_magnet_weight(magnet: dict) -> int:
    """Compute a numeric weight score for a magnet."""
    has_sub = _has_chinese_sub(magnet)
    size_mb = _parse_size_mb(magnet.get("size") or magnet.get("size_text"))
    is_large_sub = has_sub and size_mb > 2048

    file_count = magnet.get("file_count")
    if isinstance(file_count, (int, float)) and file_count > 0:
        file_penalty = max(0, 10000 - int(file_count) * 100)
    else:
        file_penalty = 5000

    return int(is_large_sub * 100000 + has_sub * 10000 + min(size_mb, 50000) + file_penalty)


class MovieMagnetRepository:
    def __init__(self, session: Session | None = None):
        self.logger = get_logger("movie_magnet_repository")
        self._session = session
        self.available = True

    def _session_scope(self):
        return self._session or get_session_factory()()

    def upsert_many(
        self,
        movie_id: Any,
        movie: dict[str, Any],
        magnets: list[dict[str, Any]],
    ) -> int:
        if not self.available:
            return 0

        saved_count = 0
        movie_id_str = str(movie_id)

        close_session = self._session is None
        session = self._session_scope()
        try:
            for magnet in magnets:
                now = datetime.now(timezone.utc)
                document = self._normalize(movie_id_str, movie, magnet, now)
                if document is None:
                    continue

                # Check if exists
                existing = session.scalar(
                    select(MovieMagnet).where(
                        MovieMagnet.movie_id == UUID(movie_id_str),
                        MovieMagnet.dedupe_key == document["dedupe_key"],
                    )
                )

                if existing:
                    # Update existing
                    for key, value in document.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                else:
                    # Create new
                    magnet_obj = MovieMagnet(
                        movie_id=UUID(movie_id_str),
                        magnet_url=document.get("magnet_url", ""),
                        info_hash=document.get("info_hash"),
                        dedupe_key=document["dedupe_key"],
                        name=document.get("name", ""),
                        size_mb=document.get("size_mb"),
                        size_text=document.get("size_text", ""),
                        file_count=document.get("file_count"),
                        file_text=document.get("file_text", ""),
                        tags=document.get("tags", []),
                        has_chinese_sub=document.get("has_chinese_sub", False),
                        date=document.get("date", ""),
                        weight=document.get("weight", 0),
                        selected=document.get("selected", False),
                        raw_data=document.get("raw_data", {}),
                    )
                    session.add(magnet_obj)

                saved_count += 1

            session.commit()
        except Exception as exc:
            session.rollback()
            self.available = False
            self.logger.warning("Failed to upsert movie magnets: %s", exc)
        finally:
            if close_session:
                session.close()

        return saved_count

    def _normalize(
        self,
        movie_id: str,
        movie: dict[str, Any],
        magnet: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        magnet_url = str(magnet.get("magnet") or magnet.get("magnet_url") or "").strip()
        name = str(magnet.get("name") or "").strip()
        size_text = str(magnet.get("size_text") or "").strip()
        file_text = str(magnet.get("file_text") or "").strip()
        if not (magnet_url or name or size_text or file_text):
            return None

        info_hash = str(magnet.get("info_hash") or "").strip().lower()
        if not info_hash:
            info_hash = extract_info_hash(magnet_url)

        tags = magnet.get("tags")
        if not isinstance(tags, list):
            tags = []

        size_mb = self._to_float(magnet.get("size"))
        if size_mb is None:
            size_mb = _parse_size_mb(magnet.get("size_text"))

        document = {
            "magnet_url": magnet_url,
            "info_hash": info_hash if info_hash else None,
            "dedupe_key": build_magnet_dedupe_key(
                movie_id,
                {
                    **magnet,
                    "magnet": magnet_url,
                    "info_hash": info_hash,
                    "name": name,
                    "size_text": size_text,
                    "file_text": file_text,
                },
            ),
            "name": name,
            "size_mb": size_mb,
            "size_text": size_text,
            "file_count": magnet.get("file_count"),
            "file_text": file_text,
            "tags": tags,
            "has_chinese_sub": bool(magnet.get("has_chinese_sub")),
            "weight": compute_magnet_weight(magnet),
            "date": magnet.get("date") or "",
            "selected": False,
            "raw_data": {},
        }
        return document

    def auto_select_best_magnet(self, movie_id: str) -> None:
        """Select the best magnet for a movie based on computed weight.

        Sets selected=True on the highest-weight magnet, False on all others.
        """
        try:
            record_id = UUID(movie_id)
        except (TypeError, ValueError):
            return

        close_session = self._session is None
        session = self._session_scope()
        try:
            magnets = session.scalars(
                select(MovieMagnet).where(MovieMagnet.movie_id == record_id)
            ).all()

            if not magnets:
                return

            # Find the magnet with the highest weight
            best = max(magnets, key=lambda m: m.weight or 0)

            # Update selected status
            for magnet in magnets:
                magnet.selected = (magnet.id == best.id)

            session.commit()
        except Exception as exc:
            session.rollback()
            self.logger.warning("Failed to auto-select best magnet for movie %s: %s", movie_id, exc)
        finally:
            if close_session:
                session.close()

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

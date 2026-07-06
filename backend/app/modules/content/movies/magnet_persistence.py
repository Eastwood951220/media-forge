from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import MovieMagnet

from backend.app.modules.content.movies.magnet_identity import build_magnet_dedupe_key, extract_info_hash
from backend.app.modules.content.movies.magnet_scoring import compute_magnet_weight, parse_size_mb


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_magnet(movie_id: UUID, magnet: dict[str, Any]) -> dict[str, Any] | None:
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

    size_mb = _to_float(magnet.get("size"))
    if size_mb is None:
        size_mb = parse_size_mb(size_text)

    return {
        "magnet_url": magnet_url,
        "info_hash": info_hash if info_hash else None,
        "dedupe_key": build_magnet_dedupe_key(str(movie_id), {**magnet, "magnet": magnet_url, "info_hash": info_hash, "name": name, "size_text": size_text, "file_text": file_text}),
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


def upsert_magnets(session: Session, movie_id: UUID, movie: dict[str, Any], magnets: list[dict[str, Any]]) -> int:
    saved_count = 0
    for magnet in magnets:
        document = normalize_magnet(movie_id, magnet)
        if document is None:
            continue
        existing = session.scalar(
            select(MovieMagnet).where(
                MovieMagnet.movie_id == movie_id,
                MovieMagnet.dedupe_key == document["dedupe_key"],
            )
        )
        if existing is None:
            session.add(MovieMagnet(movie_id=movie_id, **document))
        else:
            for key, value in document.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        saved_count += 1
    session.flush()
    if saved_count:
        auto_select_best_magnet(session, movie_id)
    return saved_count


def auto_select_best_magnet(session: Session, movie_id: UUID) -> None:
    magnets = session.scalars(select(MovieMagnet).where(MovieMagnet.movie_id == movie_id)).all()
    if not magnets:
        return
    best = max(magnets, key=lambda magnet: magnet.weight or 0)
    for magnet in magnets:
        magnet.selected = magnet.id == best.id
    session.flush()


def upsert_movie_with_magnets(session: Session, item_data: dict[str, Any]) -> UUID:
    from backend.app.modules.content.movies.movie_persistence import upsert_movie

    movie_doc = dict(item_data)
    magnets = movie_doc.pop("magnets", []) or []
    movie_id = upsert_movie(session, movie_doc)
    if magnets:
        upsert_magnets(session, movie_id, movie_doc, magnets)
    return movie_id

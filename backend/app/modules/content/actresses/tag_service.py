from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.models.content import ActressProfile, ActressTag


def normalize_actress_tag_names(tag_names: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in tag_names or []:
        name = raw_name.strip()
        if not name or name in seen:
            continue
        if len(name) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标签长度不能超过 50 个字符")
        seen.add(name)
        normalized.append(name)
    return normalized


def list_actress_tags(db: Session, owner_id: uuid.UUID) -> list[ActressTag]:
    return list(db.scalars(
        select(ActressTag)
        .where(ActressTag.owner_id == owner_id)
        .order_by(ActressTag.name.asc())
    ))


def get_or_create_actress_tags(db: Session, owner_id: uuid.UUID, tag_names: list[str]) -> list[ActressTag]:
    normalized = normalize_actress_tag_names(tag_names)
    if not normalized:
        return []
    existing = list(db.scalars(
        select(ActressTag)
        .where(ActressTag.owner_id == owner_id, ActressTag.name.in_(normalized))
    ))
    by_name = {tag.name: tag for tag in existing}
    for name in normalized:
        if name not in by_name:
            tag = ActressTag(owner_id=owner_id, name=name)
            db.add(tag)
            db.flush()
            by_name[name] = tag
    return [by_name[name] for name in normalized]


def replace_actress_tags(db: Session, profile: ActressProfile, owner_id: uuid.UUID, tag_names: list[str]) -> None:
    new_tags = get_or_create_actress_tags(db, owner_id, tag_names)
    owner_tag_ids = {tag.id for tag in list_actress_tags(db, owner_id)}
    other_owner_tags = [tag for tag in profile.tags if tag.id not in owner_tag_ids]
    profile.tags = [*other_owner_tags, *new_tags]

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.content.actresses.queries import (
    VALID_PAGE_SIZES,
    external_links_for_profile,
    list_actress_profiles,
    recent_movies_for_profile,
)
from backend.app.modules.content.actresses.schemas import ActressFetchFromTaskRequest, ActressTagsUpdateRequest
from backend.app.modules.content.actresses.serializers import serialize_actress_profile
from backend.app.modules.content.actresses.service import fetch_actresses_from_task, update_actress_tags
from backend.app.modules.content.actresses.tag_service import list_actress_tags
from shared.database.models.content import ActressProfile
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/actresses", tags=["content-actresses"])


@router.get("")
def list_actresses(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=40),
    keyword: str | None = Query(default=None, max_length=200),
    source_task_id: uuid.UUID | None = Query(default=None),
    cup: str | None = Query(default=None, max_length=20),
    height_range: str | None = Query(default=None, max_length=20),
    age_range: str | None = Query(default=None, max_length=20),
    bust_range: str | None = Query(default=None, max_length=20),
    waist_range: str | None = Query(default=None, max_length=20),
    hip_range: str | None = Query(default=None, max_length=20),
    tags: str | None = Query(default=None, max_length=500),
) -> dict:
    if limit not in VALID_PAGE_SIZES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分页大小必须是 8、16、24 或 40")
    rows, total = list_actress_profiles(
        db,
        owner_id=current_user.id,
        page=page,
        limit=limit,
        keyword=keyword,
        source_task_id=source_task_id,
        cup=cup,
        height_range=height_range,
        age_range=age_range,
        bust_range=bust_range,
        waist_range=waist_range,
        hip_range=hip_range,
        tags=tags,
    )
    return paginated(
        rows=[
            serialize_actress_profile(row, owner_id=current_user.id, external_links=external_links_for_profile(db, row))
            for row in rows
        ],
        total=total,
    )


@router.get("/tags")
def list_tags(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    return success(data=[{"id": str(tag.id), "name": tag.name} for tag in list_actress_tags(db, current_user.id)])


@router.get("/{profile_id}")
def get_actress(profile_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    profile = db.get(ActressProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="女优资料不存在")
    recent_movies = recent_movies_for_profile(db, profile, limit=10)
    external_links = external_links_for_profile(db, profile)
    return success(data=serialize_actress_profile(
        profile,
        owner_id=current_user.id,
        recent_movies=recent_movies,
        external_links=external_links,
    ))


@router.put("/{profile_id}/tags")
def update_tags(
    profile_id: uuid.UUID,
    body: ActressTagsUpdateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    profile = update_actress_tags(db, profile_id, current_user.id, body.tags)
    return success(data=serialize_actress_profile(profile, owner_id=current_user.id))


@router.post("/fetch-from-task")
def fetch_from_task(
    body: ActressFetchFromTaskRequest,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=fetch_actresses_from_task(db, body.task_id, body.task_url_id, body.avjoho_url))

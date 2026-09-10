import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.content.actresses.queries import VALID_PAGE_SIZES, list_actress_profiles, recent_movies_for_profile
from backend.app.modules.content.actresses.schemas import ActressFetchFromTaskRequest
from backend.app.modules.content.actresses.serializers import serialize_actress_profile
from backend.app.modules.content.actresses.service import fetch_actresses_from_task
from shared.database.models.content import ActressProfile
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/actresses", tags=["content-actresses"])


@router.get("")
def list_actresses(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=40),
    keyword: str | None = Query(default=None, max_length=200),
    source_task_id: uuid.UUID | None = Query(default=None),
) -> dict:
    if limit not in VALID_PAGE_SIZES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分页大小必须是 8、16、24 或 40")
    rows, total = list_actress_profiles(db, page=page, limit=limit, keyword=keyword, source_task_id=source_task_id)
    return paginated(rows=[serialize_actress_profile(row) for row in rows], total=total)


@router.get("/{profile_id}")
def get_actress(profile_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    profile = db.get(ActressProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="女优资料不存在")
    recent_movies = recent_movies_for_profile(db, profile, limit=10)
    return success(data=serialize_actress_profile(profile, recent_movies=recent_movies))


@router.post("/fetch-from-task")
def fetch_from_task(
    body: ActressFetchFromTaskRequest,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    return success(data=fetch_actresses_from_task(db, body.task_id, body.task_url_id, body.avjoho_url))

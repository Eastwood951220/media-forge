from fastapi import APIRouter, Depends
from redis import Redis
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db, get_redis
from backend.app.modules.crawler.runtime.service import get_runtime_state
from backend.app.modules.dashboard.service import build_dashboard_overview
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.schemas.common import success

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def get_dashboard_overview(current_user: CurrentUser, db: Session = Depends(get_db), ranking_cache: Redis = Depends(get_redis)) -> dict:
    overview = build_dashboard_overview(
        db=db,
        owner_id=current_user.id,
        queue_status=get_runtime_state().queue_status(),
        index_metadata=StorageIndexStore().read_metadata().to_dict(),
        ranking_cache=ranking_cache,
    )
    return success(data=overview.model_dump(mode="json"))

from fastapi import APIRouter

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.crawler.runtime.service import get_runtime_state
from shared.schemas.common import success

router = APIRouter(prefix="/api/crawler/runs", tags=["crawler-runs"])


@router.get("/queue-status")
def queue_status(_current_user: CurrentUser) -> dict:
    return success(data=get_runtime_state().queue_status())

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.dependencies import CurrentUser, get_storage_config_service
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.index.background import (
    StorageIndexAlreadyRunningError,
    start_storage_index_refresh,
)
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/index", tags=["storage-index"])


class StorageIndexRefreshRequest(BaseModel):
    mode: str = Field(default="full", pattern="^(full|incremental)$")


@router.get("/status")
def get_storage_index_status(_current_user: CurrentUser) -> dict:
    return success(data=StorageIndexStore().read_metadata().to_dict())


@router.post("/refresh")
def refresh_storage_index(
    body: StorageIndexRefreshRequest = StorageIndexRefreshRequest(),
    _current_user: CurrentUser = None,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    try:
        result = start_storage_index_refresh(
            body.mode,
            service_factory=lambda: service,
        )
    except StorageIndexAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"存储索引任务启动失败: {exc}",
        ) from exc
    return success(data=result)

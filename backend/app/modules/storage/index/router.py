from fastapi import APIRouter, Depends

from backend.app.core.dependencies import CurrentUser, get_storage_config_service
from backend.app.modules.storage.config.service import StorageConfigService
from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/index", tags=["storage-index"])


@router.get("/status")
def get_storage_index_status(_current_user: CurrentUser) -> dict:
    return success(data=StorageIndexStore().read_metadata().to_dict())


@router.post("/refresh")
def refresh_storage_index(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    with service.open_provider() as (config, provider):
        metadata = StorageIndexRefreshService().refresh(config, provider)
    return success(data=metadata.to_dict())

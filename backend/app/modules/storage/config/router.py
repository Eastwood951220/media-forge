from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.app.core.dependencies import CurrentUser, get_storage_config_service
from backend.app.modules.storage.config.schemas import StorageConfigUpdate
from backend.app.modules.storage.config.service import StorageConfigService
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/config", tags=["storage-config"])


@router.get("")
def get_storage_config(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    return success(data=service.get_config())


@router.post("/secret")
def reveal_storage_token(
    response: Response,
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return success(data={"value": str(service.get_raw_config().get("api_token") or "")})


@router.put("")
def update_storage_config(
    body: StorageConfigUpdate,
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    try:
        return success(data=service.update_config(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/test")
def test_storage_connection(
    _current_user: CurrentUser,
    service: StorageConfigService = Depends(get_storage_config_service),
) -> dict:
    return success(data=service.test_connection().model_dump())

from fastapi import APIRouter, HTTPException, status

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.jellyfin.client import JellyfinClient, JellyfinError
from backend.app.modules.scraping.config import ScrapingConfigService
from shared.schemas.common import success

router = APIRouter(prefix="/api/jellyfin", tags=["jellyfin"])


def configured_client() -> JellyfinClient:
    config = ScrapingConfigService().get_raw_config()
    return JellyfinClient(config["jellyfin_base_url"], config["jellyfin_api_key"])


@router.post("/test")
def test_connection(_current_user: CurrentUser) -> dict:
    try:
        client = configured_client()
        libraries = client.get_virtual_folders()
        root_user_id = client.get_root_user_id()
        return success(data={"library_count": len(libraries), "root_user_id": root_user_id})
    except JellyfinError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/libraries")
def get_libraries(_current_user: CurrentUser) -> dict:
    try:
        return success(data=configured_client().get_virtual_folders())
    except JellyfinError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.jellyfin.client import JellyfinClient, JellyfinError
from backend.app.modules.jellyfin.sync import config_fingerprint, get_sync_state, sync_jellyfin_watch_state
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


@router.post("/watch/sync")
def sync_watch(_current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    config = ScrapingConfigService().get_raw_config()
    try:
        result = sync_jellyfin_watch_state(db, configured_client(), fingerprint=config_fingerprint(config))
        return success(data=result.to_dict())
    except JellyfinError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/watch/status")
def get_watch_status(_current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    state = get_sync_state(db)
    config = ScrapingConfigService().get_raw_config()
    valid = state.config_fingerprint == config_fingerprint(config) and state.last_success_at is not None
    return success(data={
        "status": state.status if valid else "not_synced",
        "last_attempt_at": state.last_attempt_at.isoformat() if state.last_attempt_at else None,
        "last_success_at": state.last_success_at.isoformat() if valid else None,
        "last_error": state.last_error if valid else None,
    })

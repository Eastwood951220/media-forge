from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.scraping.config import (
    ScrapingConfigService,
    validate_run_config,
    validate_scrape_root,
)
from backend.app.modules.scraping.scan import scan_directory
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
from backend.app.modules.scraping.strm import run_strm_generation
from shared.schemas.common import success

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


@router.get("/config")
def get_scraping_config(_current_user: CurrentUser) -> dict:
    return success(data=ScrapingConfigService().get_public_config())


@router.put("/config")
def update_scraping_config(
    body: ScrapingConfigUpdate,
    _current_user: CurrentUser,
) -> dict:
    try:
        return success(data=ScrapingConfigService().update_config(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strm/run")
def run_scraping_strm(_current_user: CurrentUser) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_run_config(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return success(data=asdict(run_strm_generation(config)))


@router.post("/scan")
def scan_scraping_directory(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    config = ScrapingConfigService().get_raw_config()
    reason = validate_scrape_root(config)
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    return success(data=scan_directory(db, config).to_dict())

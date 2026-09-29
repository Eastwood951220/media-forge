from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.page_actions.auth import get_page_action_agent
from backend.app.modules.crawler.agent.page_actions.schemas import (
    AddUrlPageRunCreate,
    QuickCreatePageRunCreate,
    TemporaryPageRunCreate,
)
from backend.app.modules.crawler.agent.page_actions.service import PageActionService
from shared.schemas.common import success

router = APIRouter(
    prefix="/api/crawler/agent/page-actions",
    tags=["crawler-agent-page-actions"],
)

PageActionAgent = Annotated[CrawlerAgent, Depends(get_page_action_agent)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/tasks")
def list_page_action_tasks(agent: PageActionAgent, db: DbSession) -> dict:
    return success(data=PageActionService(db).list_enabled_tasks(agent.owner_id))


@router.post("/temporary-runs", status_code=status.HTTP_201_CREATED)
def create_temporary_page_run(
    data: TemporaryPageRunCreate,
    agent: PageActionAgent,
    db: DbSession,
) -> dict:
    result = PageActionService(db).create_temporary_run(agent.owner_id, data)
    return success(data=result.model_dump(mode="json"))


@router.post("/quick-create-runs", status_code=status.HTTP_201_CREATED)
def quick_create_page_run(
    data: QuickCreatePageRunCreate,
    agent: PageActionAgent,
    db: DbSession,
) -> dict:
    result = PageActionService(db).quick_create_run(agent.owner_id, data)
    return success(data=result.model_dump(mode="json"))


@router.post("/add-url-runs", status_code=status.HTTP_201_CREATED)
def add_url_page_run(
    data: AddUrlPageRunCreate,
    agent: PageActionAgent,
    db: DbSession,
) -> dict:
    result = PageActionService(db).add_url_run(agent.owner_id, data)
    return success(data=result.model_dump(mode="json"))

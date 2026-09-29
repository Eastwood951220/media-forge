from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.dependencies import get_db
from backend.app.models.crawler_agent import CrawlerAgent
from backend.app.modules.crawler.agent.auth import find_agent_by_token

page_action_bearer = HTTPBearer(auto_error=False)


def get_page_action_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(page_action_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> CrawlerAgent:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    agent = find_agent_by_token(db, token) if token.startswith("agt_") else None
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "msg": "Agent Token 无效或已失效",
                "data": {"reason": "invalid_agent_token"},
            },
        )
    return agent

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def constraint_name_from_integrity_error(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name:
        return str(constraint_name)

    text = str(orig or exc).lower()
    if "uq_crawl_tasks_owner_name" in text or ("crawl_tasks" in text and "owner_id" in text and "name" in text):
        return "uq_crawl_tasks_owner_name"
    if "uq_crawl_task_urls_task_url" in text or ("crawl_task_urls" in text and "task_id" in text and "url" in text):
        return "uq_crawl_task_urls_task_url"
    return ""


def raise_task_integrity_error(exc: IntegrityError, *, name: str | None = None) -> None:
    constraint_name = constraint_name_from_integrity_error(exc)
    if constraint_name == "uq_crawl_tasks_owner_name":
        msg = f"任务名称 '{name}' 已存在" if name else "任务名称已存在"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
    if constraint_name == "uq_crawl_task_urls_task_url":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 重复") from exc
    logger.exception(
        "Unexpected crawler task integrity error, constraint=%s, orig=%s",
        constraint_name or "<unknown>",
        getattr(exc, "orig", exc),
    )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="创建任务失败，请检查数据库表结构") from exc

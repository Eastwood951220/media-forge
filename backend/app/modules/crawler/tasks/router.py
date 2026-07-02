import logging
import uuid
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.runs.schemas import CrawlRunRead, RunCreateRequest
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.delete_service import delete_movies_by_task_id
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskRead,
    CrawlTaskUpdate,
    ExtractNameRequest,
)
from scraper.config.settings import REQUEST_TIMEOUT
from scraper.config.sites import JAVDB_SITE
from scraper.cookies.cookie_manager import CookieManager
from scraper.core.security import is_security_check_page
from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javdb.javdb_parser import parse_page_section_name
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/crawler/tasks", tags=["crawler-tasks"])
logger = logging.getLogger(__name__)


def _check_urls_unique(urls) -> None:
    seen: set[str] = set()
    for entry in urls:
        if entry.url in seen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"URL 重复: {entry.url}")
        seen.add(entry.url)


def _constraint_name_from_integrity_error(exc: IntegrityError) -> str:
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


def _raise_task_integrity_error(exc: IntegrityError, *, name: str | None = None) -> None:
    constraint_name = _constraint_name_from_integrity_error(exc)
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


def _serialize(task) -> CrawlTaskRead:
    data = CrawlTaskRead.model_validate(task)
    data._id = data.id
    return data


@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    return paginated(rows=[_serialize(row).model_dump(mode="json") for row in rows], total=total)


@router.get("/stats")
def get_stats(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    return success(data={"total": repo.count_by_owner(current_user.id)})


@router.post("/extract-name")
def extract_name(body: ExtractNameRequest, _current_user: CurrentUser) -> dict:
    if body.url_type == "search":
        parsed = urlparse(body.url)
        q_values = parse_qs(parsed.query).get("q", [])
        return success(data={"name": q_values[0].strip() if q_values else ""})

    try:
        cookie_manager = CookieManager(JAVDB_SITE["cookie_file"])
        fetcher = ScraplingFetcher(
            headers=JAVDB_SITE["headers"],
            cookies=cookie_manager.load(),
            timeout=REQUEST_TIMEOUT,
        )
        page = fetcher.get(body.url)
        if is_security_check_page(page):
            raise HTTPException(status_code=429, detail="触发安全验证，请稍后重试")
        return success(data={"name": parse_page_section_name(page, body.url_type)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Extract task URL name failed: %s", body.url)
        raise HTTPException(status_code=500, detail=f"提取名称失败: {exc}") from exc


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return success(data=_serialize(task).model_dump(mode="json"))


@router.post("/{task_id}/run", status_code=status.HTTP_201_CREATED)
def run_task(
    task_id: uuid.UUID,
    data: RunCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.is_skip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
    try:
        run = CrawlerRunService(db, get_runtime_state()).create_run(task, data.crawl_mode)
    except Exception as exc:
        db.rollback()
        logger.exception("Create crawler run failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
    return success(data=CrawlRunRead.model_validate(run).model_dump(mode="json"))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(data: CrawlTaskCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    if repo.get_by_name(current_user.id, data.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{data.name}' 已存在")
    _check_urls_unique(data.urls)
    try:
        created = repo.create_with_urls(
            owner_id=current_user.id,
            name=data.name,
            storage_location=data.storage_location,
            is_skip=data.is_skip,
            urls=data.urls,
        )
    except IntegrityError as exc:
        db.rollback()
        _raise_task_integrity_error(exc, name=data.name)
    return success(data=_serialize(created).model_dump(mode="json"))


@router.put("/{task_id}")
def update_task(
    task_id: uuid.UUID,
    data: CrawlTaskUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True, exclude={"urls"})
    if "name" in update_data:
        duplicate = repo.get_by_name(current_user.id, update_data["name"])
        if duplicate and duplicate.id != task.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{update_data['name']}' 已存在")

    for field, value in update_data.items():
        setattr(task, field, value)

    if data.urls is not None:
        _check_urls_unique(data.urls)
        repo.replace_urls(task, data.urls)

    try:
        updated = repo.update(task)
    except IntegrityError as exc:
        db.rollback()
        _raise_task_integrity_error(exc, name=update_data.get("name") or task.name)
    return success(data=_serialize(updated).model_dump(mode="json"))


@router.delete("/{task_id}")
def delete_task(task_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    # Cascade delete associated movies
    deleted_movies = delete_movies_by_task_id(db, task_id)
    repo.delete(task)
    return success(msg="删除成功", data={"deleted_movies": deleted_movies})

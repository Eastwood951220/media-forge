import logging
import uuid
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.dependencies import CurrentUser, get_db
from backend.app.modules.crawler.runs.schemas import CrawlRunRead, RunCreateRequest
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.delete_service import (
    UnsupportedDeleteMode,
    delete_task,
)
from backend.app.modules.crawler.tasks.errors import raise_task_integrity_error
from backend.app.modules.crawler.tasks.serializers import serialize_task
from backend.app.modules.crawler.tasks.validation import check_urls_unique, ensure_delete_mode_supported
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskCreate,
    CrawlTaskStats,
    CrawlTaskUpdate,
    ExtractNameRequest,
)
from backend.app.modules.crawler.tasks.runtime_status import (
    build_task_runtime_status_response,
    can_delete_task_runtime_status,
    get_task_runtime_status,
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


@router.get("")
def list_tasks(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=1000),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    repo = CrawlTaskRepository(db)
    rows = repo.get_by_owner(current_user.id, skip=skip, limit=limit, keyword=keyword)
    total = repo.count_by_owner(current_user.id, keyword=keyword)
    latest_runs = repo.get_latest_runs_by_task_ids([row.id for row in rows])
    return paginated(
        rows=[
            serialize_task(row, latest_runs.get(row.id)).model_dump(mode="json")
            for row in rows
        ],
        total=total,
    )


@router.get("/stats")
def get_stats(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    repo = CrawlTaskRepository(db)
    return success(data=CrawlTaskStats(**repo.get_summary_stats(current_user.id)).model_dump())


@router.get("/dict")
def task_dict(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Return task ID-to-name mapping for frontend use."""
    return success(data=CrawlTaskRepository(db).get_dict_by_owner(current_user.id))


@router.get("/statuses")
def list_task_runtime_statuses(current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    """Return derived runtime status for all tasks.

    Status is derived from each task's latest crawl run, not persisted.
    """
    payload = build_task_runtime_status_response(db, current_user.id)
    return success(data=payload.model_dump(mode="json"))


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
    return success(data=serialize_task(task).model_dump(mode="json"))


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
    check_urls_unique(data.urls)
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
        raise_task_integrity_error(exc, name=data.name)
    return success(data=serialize_task(created).model_dump(mode="json"))


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
        check_urls_unique(data.urls)
        repo.replace_urls(task, data.urls)

    try:
        updated = repo.update(task)
    except IntegrityError as exc:
        db.rollback()
        raise_task_integrity_error(exc, name=update_data.get("name") or task.name)
    return success(data=serialize_task(updated).model_dump(mode="json"))


@router.delete("/{task_id}")
def delete_task_endpoint(
    task_id: uuid.UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    mode: str = Query(default="task_only", description="Delete mode: task_only, task_and_movies, task_movies_and_cloud"),
) -> dict:
    repo = CrawlTaskRepository(db)
    task = repo.get_owned(task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Check runtime status before allowing delete
    runtime_snapshot = get_task_runtime_status(db, task_id, current_user.id)
    if runtime_snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if not can_delete_task_runtime_status(runtime_snapshot.runtime_status):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有空闲中的任务才能删除",
        )

    ensure_delete_mode_supported(mode)

    provider = None
    client = None
    if mode == "task_movies_and_cloud":
        from backend.app.modules.storage.config.service import StorageConfigService
        config_service = StorageConfigService()
        config = config_service.get_raw_config()
        client = config_service.provider_factory.create(config)
        provider = config_service.gateway_class(client)

    try:
        result = delete_task(db, task_id, mode=mode, provider=provider)
    except UnsupportedDeleteMode as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    return success(msg="删除成功", data=result.to_dict())

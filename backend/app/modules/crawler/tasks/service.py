from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.modules.crawler.runs.schemas import accepted_run_action, RunCreateRequest
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.delete_service import UnsupportedDeleteMode, delete_task
from backend.app.modules.crawler.tasks.errors import raise_task_integrity_error
from backend.app.modules.crawler.tasks.name_extractor import extract_task_name
from backend.app.modules.crawler.tasks.provider import open_delete_provider
from backend.app.modules.crawler.tasks.runtime_status import (
    can_delete_task_runtime_status,
    get_task_runtime_status,
)
from backend.app.modules.crawler.tasks.serializers import serialize_task, serialize_task_list_item
from backend.app.modules.crawler.tasks.url_detection import detect_task_url_type
from backend.app.modules.crawler.tasks.validation import (
    check_urls_unique,
    ensure_delete_mode_supported,
    normalize_temporary_detail_urls,
)
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import (
    CrawlTaskBatchCreate,
    CrawlTaskBatchCreateResult,
    CrawlTaskBatchCreatedItem,
    CrawlTaskBatchFailedItem,
    CrawlTaskBatchRunAcceptedItem,
    CrawlTaskBatchRunCreate,
    CrawlTaskBatchRunFailedItem,
    CrawlTaskBatchRunResult,
    CrawlTaskCreate,
    CrawlTaskListResponse,
    CrawlTaskUpdate,
    CrawlTaskUrlRunCreate,
    ExtractNameRequest,
    TaskUrlEntryCreate,
    TemporaryCrawlRunCreate,
)
from scraper.tasks.task_utils import determine_source

logger = logging.getLogger(__name__)


def normalize_tag_names(tag_names: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in tag_names or []:
        name = raw_name.strip()
        if not name or name in seen:
            continue
        if len(name) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标签长度不能超过 50 个字符")
        seen.add(name)
        normalized.append(name)
    return normalized


class CrawlerTaskService:
    """Application service for crawler task operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CrawlTaskRepository(db)

    def list_tasks(
        self,
        owner_id: uuid.UUID,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        tag_names: list[str] | None = None,
    ) -> dict:
        rows, _ = self.repo.get_by_owner(owner_id, page=page, size=size, keyword=keyword, tag_names=tag_names)
        total = self.repo.count_by_owner(owner_id, keyword=keyword, tag_names=tag_names)
        return CrawlTaskListResponse(
            rows=[serialize_task_list_item(row) for row in rows],
            total=total,
            page=page,
            size=size,
        ).model_dump(mode="json")

    def task_dict(self, owner_id: uuid.UUID) -> dict:
        return self.repo.get_dict_by_owner(owner_id)

    def list_task_tags(self, owner_id: uuid.UUID) -> list[dict[str, str]]:
        return [{"id": str(tag.id), "name": tag.name} for tag in self.repo.get_tags_by_owner(owner_id)]

    def _tags_for_names(self, owner_id: uuid.UUID, tag_names: list[str] | None):
        return self.repo.get_or_create_tags(owner_id, normalize_tag_names(tag_names))

    def get_task(self, task_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return serialize_task(task).model_dump(mode="json")

    def run_task(
        self,
        task_id: uuid.UUID,
        data: RunCreateRequest,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
        try:
            run = CrawlerRunService(self.db, get_runtime_state()).create_run(task, data.crawl_mode)
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create crawler run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return accepted_run_action(run.id)

    def create_url_subset_run(
        self,
        task_id: uuid.UUID,
        data: CrawlTaskUrlRunCreate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")

        selected_ids = list(data.url_ids)
        if not selected_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择 1 条任务 URL")
        if len(set(selected_ids)) != len(selected_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 URL 不能重复选择")

        task_url_ids = {row.id for row in task.urls}
        if not set(selected_ids).issubset(task_url_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="选择的 URL 不属于该任务")

        try:
            run = CrawlerRunService(self.db, get_runtime_state()).create_run(
                task,
                data.crawl_mode,
                selected_task_url_ids=selected_ids,
            )
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create crawler URL subset run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return accepted_run_action(run.id)

    def create_temporary_run(
        self,
        data: TemporaryCrawlRunCreate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(data.task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if task.is_skip:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="禁用任务不能执行")
        try:
            detail_urls = normalize_temporary_detail_urls(data.detail_urls)
            run = CrawlerRunService(self.db, get_runtime_state()).create_temporary_detail_run(task, detail_urls)
        except ValueError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            self.db.rollback()
            logger.exception("Create temporary crawler run failed")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"任务运行时不可用: {exc}") from exc
        return accepted_run_action(run.id)

    def create_task(self, data: CrawlTaskCreate, owner_id: uuid.UUID) -> dict:
        if self.repo.get_by_name(owner_id, data.name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{data.name}' 已存在")
        check_urls_unique(data.urls)
        # Validate tag names before any database writes so a 400 leaves nothing behind.
        if data.tag_names is not None:
            normalize_tag_names(data.tag_names)
        try:
            created = self.repo.create_with_urls(
                owner_id=owner_id,
                name=data.name,
                storage_location=data.storage_location,
                is_skip=data.is_skip,
                urls=data.urls,
            )
            if data.tag_names is not None:
                self.repo.replace_task_tags(created, self._tags_for_names(owner_id, data.tag_names))
                self.db.commit()
                self.db.refresh(created)
                created = self.repo.get_owned(created.id, owner_id) or created
        except ValueError as exc:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except IntegrityError as exc:
            self.db.rollback()
            raise_task_integrity_error(exc, name=data.name)
        return serialize_task(created).model_dump(mode="json")

    def _unique_task_name(self, owner_id: uuid.UUID, base_name: str, reserved: set[str]) -> str:
        candidate = base_name
        suffix = 2
        while candidate in reserved or self.repo.get_by_name(owner_id, candidate):
            candidate = f"{base_name} ({suffix})"
            suffix += 1
        reserved.add(candidate)
        return candidate

    def batch_create_tasks(self, data: CrawlTaskBatchCreate, owner_id: uuid.UUID) -> dict:
        normalized_urls = [url.strip() for url in data.urls if url.strip()]
        if not normalized_urls:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少提供 1 个 URL")
        # Validate tag names once so an invalid batch payload fails before any item runs.
        if data.tag_names is not None:
            normalize_tag_names(data.tag_names)

        created: list[CrawlTaskBatchCreatedItem] = []
        failed: list[CrawlTaskBatchFailedItem] = []
        seen_urls: set[str] = set()
        reserved_names: set[str] = set()

        for url in normalized_urls:
            if url in seen_urls:
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="URL 重复"))
                continue
            seen_urls.add(url)

            source = determine_source(url)
            if source == "unknown":
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="不支持的 URL 来源"))
                continue

            url_type = detect_task_url_type(url, source)
            if not url_type:
                failed.append(CrawlTaskBatchFailedItem(url=url, reason="无法识别 URL 类型"))
                continue

            try:
                extracted_name = extract_task_name(ExtractNameRequest(url=url, url_type=url_type)).strip()
                if not extracted_name:
                    raise ValueError("未解析到 URL 名称")
                task_name = self._unique_task_name(owner_id, extracted_name, reserved_names)
                task_url = TaskUrlEntryCreate(
                    url=url,
                    url_type=url_type,
                    has_magnet=data.has_magnet,
                    has_chinese_sub=data.has_chinese_sub,
                    sort_type=data.sort_type,
                    url_name=extracted_name,
                )
                task = self.repo.create_with_urls(
                    owner_id=owner_id,
                    name=task_name,
                    storage_location=task_name,
                    is_skip=data.is_skip,
                    urls=[task_url],
                )
                if data.tag_names is not None:
                    self.repo.replace_task_tags(task, self._tags_for_names(owner_id, data.tag_names))
                    self.db.commit()
                    self.db.refresh(task)
                created.append(CrawlTaskBatchCreatedItem(url=url, task=serialize_task(task)))
            except HTTPException as exc:
                self.db.rollback()
                failed.append(CrawlTaskBatchFailedItem(url=url, reason=str(exc.detail)))
            except Exception as exc:
                self.db.rollback()
                failed.append(CrawlTaskBatchFailedItem(url=url, reason=str(exc)))

        return CrawlTaskBatchCreateResult(
            created=created,
            failed=failed,
            created_count=len(created),
            failed_count=len(failed),
        ).model_dump(mode="json")

    def update_task(
        self,
        task_id: uuid.UUID,
        data: CrawlTaskUpdate,
        owner_id: uuid.UUID,
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        update_data = data.model_dump(exclude_unset=True, exclude={"urls", "tag_names"})
        if "name" in update_data:
            duplicate = self.repo.get_by_name(owner_id, update_data["name"])
            if duplicate and duplicate.id != task.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务名称 '{update_data['name']}' 已存在")

        # Validate tag names before mutating anything else.
        if data.tag_names is not None:
            normalize_tag_names(data.tag_names)

        for field, value in update_data.items():
            setattr(task, field, value)

        if data.urls is not None:
            check_urls_unique(data.urls)
            try:
                self.repo.replace_urls(task, data.urls)
            except ValueError as exc:
                self.db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        if data.tag_names is not None:
            self.repo.replace_task_tags(task, self._tags_for_names(owner_id, data.tag_names))

        try:
            updated = self.repo.update(task)
        except IntegrityError as exc:
            self.db.rollback()
            raise_task_integrity_error(exc, name=update_data.get("name") or task.name)
        return serialize_task(updated).model_dump(mode="json")

    def _unique_task_ids(self, task_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        unique_ids: list[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for task_id in task_ids:
            if task_id in seen:
                continue
            seen.add(task_id)
            unique_ids.append(task_id)
        return unique_ids

    def batch_run_tasks(self, data: CrawlTaskBatchRunCreate, owner_id: uuid.UUID) -> dict:
        accepted: list[CrawlTaskBatchRunAcceptedItem] = []
        failed: list[CrawlTaskBatchRunFailedItem] = []

        for task_id in self._unique_task_ids(list(data.task_ids)):
            task = self.repo.get_owned(task_id, owner_id)
            if task is None:
                failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason="Task not found"))
                continue
            if task.is_skip:
                failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason="禁用任务不能执行"))
                continue
            try:
                run = CrawlerRunService(self.db, get_runtime_state()).create_run(task, data.crawl_mode)
                accepted.append(CrawlTaskBatchRunAcceptedItem(task_id=task_id, run_id=run.id))
            except Exception as exc:
                self.db.rollback()
                logger.exception("Create crawler batch run failed for task %s", task_id)
                failed.append(CrawlTaskBatchRunFailedItem(task_id=task_id, reason=f"任务运行时不可用: {exc}"))

        return CrawlTaskBatchRunResult(
            accepted=accepted,
            failed=failed,
            accepted_count=len(accepted),
            failed_count=len(failed),
        ).model_dump(mode="json")

    def delete_task(
        self,
        task_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        mode: str = "task_only",
    ) -> dict:
        task = self.repo.get_owned(task_id, owner_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        runtime_snapshot = get_task_runtime_status(self.db, task_id, owner_id)
        if runtime_snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if not can_delete_task_runtime_status(runtime_snapshot.runtime_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有空闲中的任务才能删除",
            )

        ensure_delete_mode_supported(mode)

        run_ids = [
            str(row.id)
            for row in self.db.query(CrawlRun.id)
            .filter(CrawlRun.task_id == task_id)
            .all()
        ]

        try:
            with open_delete_provider(mode) as provider:
                result = delete_task(self.db, task_id, mode=mode, provider=provider)
                get_runtime_state().purge_runs(run_ids)
        except UnsupportedDeleteMode as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        return result.to_dict()

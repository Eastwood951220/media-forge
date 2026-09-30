from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.crawl_run import CrawlRun
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.modules.crawler.agent.page_actions.schemas import (
    AddUrlPageRunCreate,
    PageActionRunResult,
    QuickCreatePageRunCreate,
    TemporaryPageRunCreate,
)
from backend.app.modules.crawler.agent.page_actions.urls import normalize_javdb_list_url
from backend.app.modules.crawler.runtime.service import CrawlerRunService, get_runtime_state
from backend.app.modules.crawler.tasks.errors import raise_task_integrity_error
from backend.app.modules.crawler.tasks.validation import normalize_temporary_detail_urls
from backend.app.repositories.crawl_task import CrawlTaskRepository
from backend.app.schemas.crawl_task import TaskUrlEntryCreate

logger = logging.getLogger(__name__)


def _page_action_error(status_code: int, message: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"msg": message, "data": {"reason": reason}},
    )


class PageActionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CrawlTaskRepository(db)

    def list_enabled_tasks(self, owner_id: uuid.UUID) -> list[dict[str, str]]:
        return self.repo.get_enabled_dict_by_owner(owner_id)

    def _require_enabled_task(
        self,
        task_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> CrawlTask:
        task = (
            self.repo.get_owned_for_update(task_id, owner_id)
            if for_update
            else self.repo.get_owned(task_id, owner_id)
        )
        if task is None:
            raise _page_action_error(
                status.HTTP_404_NOT_FOUND,
                "任务不存在或无权访问",
                "task_not_found",
            )
        if task.is_skip:
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                "禁用任务不能执行",
                "task_disabled",
            )
        return task

    def create_temporary_run(
        self,
        owner_id: uuid.UUID,
        data: TemporaryPageRunCreate,
    ) -> PageActionRunResult:
        task = self._require_enabled_task(data.task_id, owner_id)
        try:
            detail_url = normalize_temporary_detail_urls([data.detail_url])[0]
        except ValueError as exc:
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                str(exc),
                "invalid_detail_url",
            ) from exc

        run_service = CrawlerRunService(self.db, get_runtime_state())
        try:
            run = run_service.prepare_temporary_detail_run(task, [detail_url])
            self.db.commit()
            self.db.refresh(run)
        except Exception as exc:
            self.db.rollback()
            logger.error(
                "Create temporary Agent page-action run failed: error_type=%s",
                type(exc).__name__,
            )
            raise _page_action_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "临时运行创建失败",
                "runtime_unavailable",
            ) from exc
        return self._activate_result(run_service, task, run, crawl_mode="temporary")

    def _activate_result(
        self,
        run_service: CrawlerRunService,
        task: CrawlTask,
        run: CrawlRun,
        *,
        crawl_mode: str,
        url_entry_id: uuid.UUID | None = None,
        url_added: bool | None = None,
    ) -> PageActionRunResult:
        accepted = True
        runtime_error = None
        try:
            run_service.activate_run(run)
        except Exception as exc:
            accepted = False
            runtime_error = "运行记录已创建，但爬虫运行时启动失败"
            logger.error(
                "Activate Agent page-action run failed: run_id=%s error_type=%s",
                run.id,
                type(exc).__name__,
            )
        return PageActionRunResult(
            task_id=task.id,
            task_name=task.name,
            run_id=run.id,
            crawl_mode=crawl_mode,
            accepted=accepted,
            runtime_error=runtime_error,
            url_entry_id=url_entry_id,
            url_added=url_added,
        )

    def quick_create_run(
        self,
        owner_id: uuid.UUID,
        data: QuickCreatePageRunCreate,
    ) -> PageActionRunResult:
        name = data.name.strip()
        page_name = data.page_name.strip()
        if not name:
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                "任务名称不能为空",
                "invalid_task_name",
            )
        try:
            normalized = normalize_javdb_list_url(data.list_url)
        except ValueError as exc:
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                str(exc),
                "invalid_list_url",
            ) from exc
        if self.repo.get_by_name(owner_id, name) is not None:
            raise _page_action_error(
                status.HTTP_409_CONFLICT,
                f"任务名称 '{name}' 已存在",
                "duplicate_task_name",
            )

        entry = TaskUrlEntryCreate(
            url=normalized.url,
            final_url=normalized.url,
            url_type=normalized.url_type,
            url_name=page_name,
        )
        try:
            task = self.repo.add_with_urls(
                owner_id=owner_id,
                name=name,
                storage_location=name,
                is_skip=False,
                urls=[entry],
            )
            run_service = CrawlerRunService(self.db, get_runtime_state())
            run = run_service.prepare_run(task, "full")
            self.db.commit()
            self.db.refresh(task)
            self.db.refresh(run)
        except IntegrityError as exc:
            self.db.rollback()
            raise_task_integrity_error(exc, name=name)
        except ValueError as exc:
            self.db.rollback()
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                str(exc),
                "invalid_list_url",
            ) from exc
        return self._activate_result(run_service, task, run, crawl_mode="full")

    @staticmethod
    def _find_normalized_url(task: CrawlTask, normalized_url: str) -> CrawlTaskUrl | None:
        for row in task.urls:
            if row.url == normalized_url:
                return row
            try:
                if normalize_javdb_list_url(row.url).url == normalized_url:
                    return row
            except ValueError:
                continue
        return None

    def _prepare_add_url_run(
        self,
        task: CrawlTask,
        normalized_url: str,
        entry: TaskUrlEntryCreate,
    ) -> tuple[CrawlTaskUrl, bool, CrawlerRunService, CrawlRun]:
        url_entry = self._find_normalized_url(task, normalized_url)
        url_added = url_entry is None
        if url_entry is None:
            url_entry = self.repo.append_url(task, entry)
        run_service = CrawlerRunService(self.db, get_runtime_state())
        run = run_service.prepare_run(
            task,
            "incremental",
            selected_task_url_ids=[url_entry.id],
        )
        return url_entry, url_added, run_service, run

    def add_url_run(
        self,
        owner_id: uuid.UUID,
        data: AddUrlPageRunCreate,
    ) -> PageActionRunResult:
        try:
            normalized = normalize_javdb_list_url(data.list_url)
        except ValueError as exc:
            raise _page_action_error(
                status.HTTP_400_BAD_REQUEST,
                str(exc),
                "invalid_list_url",
            ) from exc
        entry = TaskUrlEntryCreate(
            url=normalized.url,
            final_url=normalized.url,
            url_type=normalized.url_type,
            url_name=data.page_name.strip(),
        )
        task = self._require_enabled_task(data.task_id, owner_id, for_update=True)
        try:
            url_entry, url_added, run_service, run = self._prepare_add_url_run(
                task,
                normalized.url,
                entry,
            )
            self.db.commit()
            self.db.refresh(run)
        except IntegrityError:
            self.db.rollback()
            task = self._require_enabled_task(data.task_id, owner_id, for_update=True)
            url_entry = self._find_normalized_url(task, normalized.url)
            if url_entry is None:
                raise _page_action_error(
                    status.HTTP_409_CONFLICT,
                    "任务 URL 添加冲突，请重试",
                    "task_url_conflict",
                )
            run_service = CrawlerRunService(self.db, get_runtime_state())
            run = run_service.prepare_run(
                task,
                "incremental",
                selected_task_url_ids=[url_entry.id],
            )
            self.db.commit()
            self.db.refresh(run)
            url_added = False
        return self._activate_result(
            run_service,
            task,
            run,
            crawl_mode="incremental",
            url_entry_id=url_entry.id,
            url_added=url_added,
        )

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.tasks.policies import is_vr_movie_tags
from backend.app.modules.storage.worker.download import recover_existing_downloaded_video_files
from backend.app.modules.storage.worker.download_flow import run_download_flow
from backend.app.modules.storage.worker.existing_target_flow import handle_existing_target_fallback
from backend.app.modules.storage.worker.file_pipeline import run_found_files_pipeline
from backend.app.modules.storage.worker.attempts import (
    append_magnet_attempt,
    mark_magnet_attempt_success,
    ordered_magnet_attempts,
)
from backend.app.modules.storage.worker.cleanup_ops import cleanup_download_folder
from backend.app.modules.storage.worker.existing_movie_storage import copy_from_existing_movie_storage
from backend.app.modules.storage.worker.results import mark_subtask_success_from_existing_movie_storage
from backend.app.modules.storage.worker.target_planning import plan_storage_attempt
from backend.app.modules.storage.worker.verify_ops import verify_moved_files

logger = logging.getLogger(__name__)


def _subtask_log(context, level: str, message: str, extra: dict | None = None) -> None:
    subtask_id = getattr(context.subtask, "id", None)
    if subtask_id is None:
        return
    write_storage_subtask_log(str(subtask_id), level, message, extra or {})


def _capture_failed_attempt(context, magnet: dict) -> dict | None:
    download_folder = str(getattr(context.subtask, "download_path", "") or "")
    target_paths = list(getattr(context.subtask, "target_paths", None) or [])
    if not download_folder or not target_paths:
        return None
    return {
        "magnet": magnet,
        "download_folder": download_folder,
        "target_paths": target_paths,
    }


def _wait_before_next_magnet(context) -> None:
    wait_seconds = float(context.config.get("download_initial_wait_seconds", 60.0) or 0)
    if wait_seconds <= 0:
        return
    context.log(
        "INFO",
        f"磁力尝试间隔等待 {wait_seconds:g} 秒",
        {"wait_seconds": wait_seconds},
        step="waiting_download",
    )
    time.sleep(wait_seconds)


def _recover_failed_attempts(context, failed_attempts: list[dict], config: dict) -> bool:
    download_root = config.get("download_root_folder", "/Downloads")
    search_terms = [context.subtask.movie_code]
    for attempt in failed_attempts:
        download_folder = attempt["download_folder"]
        found_files = recover_existing_downloaded_video_files(
            context,
            search_terms,
            download_folder,
            download_root,
            recovery_reason="prior_magnet_attempt",
        )
        if not found_files:
            continue
        magnet = attempt["magnet"]
        context.log(
            "INFO",
            "前序磁力已完成，使用该磁力结果",
            {
                "magnet_id": magnet.get("id"),
                "download_folder": download_folder,
                "file_count": len(found_files),
            },
            step="waiting_download",
        )
        success = run_found_files_pipeline(
            context,
            magnet,
            found_files,
            attempt["target_paths"],
            download_folder,
            config,
        )
        if success:
            mark_magnet_attempt_success(context.subtask, magnet)
            return True
    return False


def execute_current_magnet_attempt(context, magnet: dict, movie=None, movie_tags: list[str] | None = None) -> bool:
    """Execute a single magnet download attempt through the full step pipeline."""
    subtask = context.subtask
    config = context.config
    magnet_url = magnet.get("magnet_url", "")
    if not magnet_url:
        context.log("WARNING", "磁力缺少链接", {"magnet_id": magnet.get("id")}, step="prepare")
        return False

    context.set_step("prepare")
    plan = plan_storage_attempt(subtask, config, magnet, movie_tags=movie_tags)
    download_root = plan.download_root
    download_folder = plan.download_folder
    preview_name = plan.preview_name
    target_paths = plan.target_paths
    tags = list(magnet.get("tags") or [])
    prepare_context = {"download_path": download_folder, "target_paths": target_paths, "magnet_id": magnet.get("id")}
    if is_vr_movie_tags(list(movie_tags or [])):
        prepare_context.update({"vr_detected": True, "vr_source": "movie_tags"})
    context.log(
        "INFO",
        f"准备完成: download={download_folder}, target={target_paths[-1]}, targets={target_paths}, suffix={preview_name.replace(subtask.movie_code.upper(), '').rsplit('.', 1)[0]}",
        prepare_context,
        step="prepare",
    )

    if movie is not None:
        try:
            copied_files = copy_from_existing_movie_storage(context, movie, target_paths)
        except Exception as exc:
            context.log(
                "WARNING",
                "电影已有存储复制失败，继续磁力流程",
                {"magnet_id": magnet.get("id"), "error": str(exc), "target_paths": target_paths},
                step="prepare",
            )
        else:
            if copied_files:
                context.set_step("verify_result")
                if verify_moved_files(context, copied_files):
                    context.set_step("cleanup_files")
                    cleanup_download_folder(context, download_folder, config)
                    mark_subtask_success_from_existing_movie_storage(context, copied_files, magnet)
                    return True
                context.log(
                    "WARNING",
                    "电影已有存储复制验证失败，继续磁力流程",
                    {"magnet_id": magnet.get("id"), "files": copied_files},
                    step="verify_result",
                )

    download_result = run_download_flow(context, magnet, download_folder, download_root)
    if download_result is None:
        return False
    found_files = download_result.found_files
    if not found_files:
        context.log(
            "WARNING",
            "未在下载目录找到可用视频文件",
            {"magnet_id": magnet.get("id"), "task_download_folder": download_folder, "download_root": download_root},
            step="waiting_download",
        )
        if download_result.submit_task_exists:
            fallback_result = handle_existing_target_fallback(context, magnet, preview_name, target_paths, download_folder, config)
            if fallback_result is not None:
                return fallback_result
        return False
    return run_found_files_pipeline(context, magnet, found_files, target_paths, download_folder, config)


def execute_subtask_pipeline(context) -> None:
    """Execute the full subtask pipeline."""
    subtask = context.subtask
    config = context.config

    subtask.status = "running"
    subtask.step = "prepare"
    subtask.started_at = datetime.now(timezone.utc)
    context.publish_subtask()

    context.log("INFO", "存储子任务 pipeline 开始", {"movie_id": str(subtask.movie_id)})

    # Get magnets for this movie
    from shared.database.models.content import Movie
    movie = context.db.get(Movie, subtask.movie_id)
    if movie is None:
        subtask.status = "failed"
        subtask.error_message = "电影不存在"
        subtask.finished_at = datetime.now(timezone.utc)
        context.publish_subtask()
        return

    # Order magnets by priority
    ordered = ordered_magnet_attempts(movie, int(config.get("magnet_max_attempts_per_subtask", 3)))
    if not ordered:
        subtask.status = "failed"
        subtask.error_message = "无可用磁力链接"
        subtask.finished_at = datetime.now(timezone.utc)
        context.publish_subtask()
        return

    failed_attempts: list[dict] = []

    # Try each magnet
    for attempt_index, magnet in enumerate(ordered, start=1):
        if failed_attempts:
            _wait_before_next_magnet(context)
            if _recover_failed_attempts(context, failed_attempts, config):
                if subtask.status != "skipped":
                    subtask.status = "completed"
                subtask.step = "done"
                subtask.finished_at = datetime.now(timezone.utc)
                context.publish_subtask()
                return

        magnet = {**magnet, "attempt_index": attempt_index}
        subtask.step = "prepare"
        subtask.current_magnet_id = magnet.get("id")
        subtask.current_magnet_url = magnet.get("magnet_url", "")
        context.publish_subtask()

        context.log(
            "INFO",
            "开始尝试磁力",
            {
                "magnet_id": magnet.get("id"),
                "weight": magnet.get("weight"),
                "selected": magnet.get("selected"),
            },
        )

        success = execute_current_magnet_attempt(context, magnet, movie=movie, movie_tags=list(movie.tags or []))

        context.log(
            "INFO" if success else "WARNING",
            "磁力尝试完成" if success else "磁力尝试失败，准备尝试下一条",
            {"magnet_id": magnet.get("id"), "success": success},
        )

        append_magnet_attempt(subtask, magnet, success)

        if success:
            if subtask.status != "skipped":
                subtask.status = "completed"
            subtask.step = "done"
            subtask.finished_at = datetime.now(timezone.utc)
            context.publish_subtask()
            return
        failed_attempt = _capture_failed_attempt(context, magnet)
        if failed_attempt is not None:
            failed_attempts.append(failed_attempt)

    # All magnets failed
    subtask.status = "failed"
    subtask.error_message = "所有磁力链接尝试均失败"
    subtask.finished_at = datetime.now(timezone.utc)
    context.publish_subtask()

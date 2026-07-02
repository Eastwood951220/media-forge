"""Compatibility routes for the old /api/crawl-tasks prefix.

New frontend code uses /api/crawler/tasks. Keep this prefix temporarily so a
stale browser tab or cached bundle cannot reproduce the pasted 500 error.
"""

from fastapi import APIRouter

from backend.app.modules.crawler.tasks.router import (
    create_task,
    delete_task,
    get_stats,
    get_task,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/api/crawl-tasks", tags=["crawl-tasks-compat"])

router.add_api_route("", list_tasks, methods=["GET"])
router.add_api_route("/stats", get_stats, methods=["GET"])
router.add_api_route("/{task_id}", get_task, methods=["GET"])
router.add_api_route("", create_task, methods=["POST"], status_code=201)
router.add_api_route("/{task_id}", update_task, methods=["PUT"])
router.add_api_route("/{task_id}", delete_task, methods=["DELETE"], status_code=204)

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.dependencies import CurrentUser, get_storage_task_service
from backend.app.modules.storage.tasks.schemas import StorageBatchPushRequest, StorageSinglePushRequest
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/tasks", tags=["storage-tasks"])


@router.get("/next-alias")
def get_next_alias(current_user: CurrentUser, service=Depends(get_storage_task_service)):
    return success(data={"alias": service.generate_next_alias()})


@router.post("/push")
def create_single_storage_push(body: StorageSinglePushRequest, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.create_single_push(body, current_user.id)
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/batch")
def create_batch_storage_push(body: StorageBatchPushRequest, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.create_batch_push(body, current_user.id)
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Subtask detail and logs (MUST be before /{main_task_id} routes) ---


@router.get("/subtasks/{subtask_id}")
def get_storage_subtask(subtask_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    subtask = service.repository.get_subtask(subtask_id)
    if subtask is None:
        raise HTTPException(status_code=404, detail="Subtask not found")
    return success(data=service.to_subtask_response(subtask))


@router.get("/subtasks/{subtask_id}/logs")
def get_storage_subtask_logs(subtask_id: UUID, current_user: CurrentUser):
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs

    logs = read_storage_subtask_logs(str(subtask_id))
    return success(data=logs)


# --- Main task list, detail, and subtask listing ---


@router.get("")
def list_storage_main_tasks(
    current_user: CurrentUser,
    service=Depends(get_storage_task_service),
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    keyword: str | None = None,
):
    rows, total = service.repository.list_main_tasks(page=page, limit=limit, status=status, keyword=keyword)
    return success(data={
        "rows": [service.to_main_response(r) for r in rows],
        "total": total,
    })


@router.get("/{main_task_id}")
def get_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    task = service.repository.get_main(main_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return success(data=service.to_main_response(task))


@router.delete("/{main_task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        service.delete_main_task(main_task_id, current_user.id)
        return None
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{main_task_id}/subtasks")
def list_storage_subtasks(
    main_task_id: UUID,
    current_user: CurrentUser,
    service=Depends(get_storage_task_service),
    page: int = 1,
    limit: int = 20,
):
    task = service.repository.get_main(main_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    rows, total = service.repository.list_subtasks(main_task_id, page=page, limit=limit)
    return success(data={
        "rows": [service.to_subtask_response(r) for r in rows],
        "total": total,
    })


@router.post("/{main_task_id}/stop")
def stop_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.stop_main_task(main_task_id)
        if task.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{main_task_id}/restart")
def restart_storage_main_task(main_task_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
    try:
        task = service.restart_main_task(main_task_id)
        if task.created_by != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return success(data=service.to_main_response(task))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

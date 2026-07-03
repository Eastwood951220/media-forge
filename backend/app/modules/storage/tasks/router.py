from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.dependencies import CurrentUser, get_storage_task_service
from backend.app.modules.storage.tasks.schemas import StorageBatchPushRequest, StorageSinglePushRequest
from shared.schemas.common import success

router = APIRouter(prefix="/api/storage/tasks", tags=["storage-tasks"])


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

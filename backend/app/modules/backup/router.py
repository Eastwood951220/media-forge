from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from backend.app.core.dependencies import CurrentUser
from backend.app.modules.backup.config import BackupConfigService
from backend.app.modules.backup.jobs import backup_job_registry
from backend.app.modules.backup.paths import safe_backup_file_path
from backend.app.modules.backup.schemas import (
    BackupConfigUpdate,
    BackupExportRequest,
    BackupJobResponse,
    BackupRestoreRequest,
)
from backend.app.modules.backup.scheduler import backup_scheduler
from backend.app.modules.backup.service import BackupService
from shared.schemas.common import success

router = APIRouter(prefix="/api/backup", tags=["backup"])


def get_backup_config_service() -> BackupConfigService:
    return BackupConfigService()


def _validate_restore_payload(payload_text: str) -> BackupRestoreRequest:
    if not payload_text.strip():
        return BackupRestoreRequest()
    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的恢复参数") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的恢复参数")
    try:
        return BackupRestoreRequest(**raw)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _save_upload(upload: UploadFile) -> Path:
    """Persist an uploaded archive to a temp file with a safe generated name."""
    if not upload.filename or not upload.filename.endswith(".mfbackup"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .mfbackup 备份文件")
    temp_path = Path(tempfile.gettempdir()) / f"backup-upload-{uuid.uuid4().hex}.mfbackup"
    try:
        with temp_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无法读取上传文件: {exc}") from exc
    finally:
        upload.file.close()
    return temp_path


@router.get("/config")
def get_backup_config(_current_user: CurrentUser) -> dict:
    service = get_backup_config_service()
    return success(data=service.get_config().model_dump())


@router.put("/config")
def update_backup_config(body: BackupConfigUpdate, _current_user: CurrentUser) -> dict:
    service = get_backup_config_service()
    try:
        config = service.update_config(body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    backup_scheduler.refresh()
    return success(data=config.model_dump())


@router.get("/files")
def list_backup_files(_current_user: CurrentUser) -> dict:
    service = BackupService()
    return success(
        data=[info.model_dump(mode="json") for info in service.list_files()]
    )


@router.post("/export")
def start_export(body: BackupExportRequest, current_user: CurrentUser) -> dict:
    job = backup_job_registry.create("export")
    service = BackupService()
    service.start_export_job(job.id, body, current_user.id)
    return success(data=BackupJobResponse(job_id=job.id).model_dump(mode="json"))


@router.get("/files/{name}/download")
def download_backup_file(name: str, _current_user: CurrentUser) -> FileResponse:
    config = get_backup_config_service().get_config()
    backup_dir = Path(config.backup_dir)
    try:
        path = safe_backup_file_path(backup_dir, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份文件不存在")
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/inspect")
def inspect_backup(
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> dict:
    """Upload an archive for preflight inspection without restoring it."""
    del current_user
    temp_path = _save_upload(file)
    try:
        service = BackupService()
        inspected = service.inspect_file(temp_path)
        return success(data=inspected.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/restore")
def restore_backup_upload(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    payload: str = Form(default='{"mode": "merge"}'),
) -> dict:
    """Upload an archive and restore it through an in-process job."""
    request = _validate_restore_payload(payload)
    temp_path = _save_upload(file)
    job = backup_job_registry.create("restore")
    service = BackupService()
    service.start_restore_job(job.id, temp_path, request, current_user.id, delete_after=True)
    return success(data=BackupJobResponse(job_id=job.id).model_dump(mode="json"))


@router.post("/files/{name}/restore")
def restore_backup_file(
    name: str,
    body: BackupRestoreRequest,
    current_user: CurrentUser,
) -> dict:
    config = get_backup_config_service().get_config()
    backup_dir = Path(config.backup_dir)
    try:
        path = safe_backup_file_path(backup_dir, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份文件不存在")
    job = backup_job_registry.create("restore")
    service = BackupService()
    service.start_restore_job(job.id, path, body, current_user.id, delete_after=False)
    return success(data=BackupJobResponse(job_id=job.id).model_dump(mode="json"))


@router.delete("/files/{name}")
def delete_backup_file(name: str, _current_user: CurrentUser) -> dict:
    service = BackupService()
    try:
        result = service.delete_file(name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return success(data=result)


@router.get("/jobs/{job_id}")
def get_backup_job(job_id: uuid.UUID, _current_user: CurrentUser) -> dict:
    job = backup_job_registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份任务不存在")
    return success(data=job.model_dump(mode="json"))

from __future__ import annotations

import grpc

from shared.integrations.storage_providers.clouddrive2.exceptions import (
    CloudDriveAuthenticationError,
    CloudDriveConnectionError,
    CloudDriveNotFoundError,
    CloudDriveOperationError,
    CloudDrivePermissionError,
    CloudDriveRateLimitError,
)
from shared.integrations.storage_providers.clouddrive2.models import (
    RemoteFile,
    RemoteOperationResult,
)


def map_remote_file(file_obj) -> RemoteFile:
    return RemoteFile(
        name=file_obj.name,
        full_path=file_obj.fullPathName if hasattr(file_obj, "fullPathName") else file_obj.name,
        size=file_obj.size,
        is_directory=file_obj.isDirectory if hasattr(file_obj, "isDirectory") else False,
    )


def map_operation_result(result_obj) -> RemoteOperationResult:
    return RemoteOperationResult(
        success=bool(getattr(result_obj, "success", False)),
        error_message=getattr(result_obj, "errorMessage", None) or None,
        result_paths=list(getattr(result_obj, "resultFilePaths", [])),
    )


def map_grpc_error(exc: grpc.RpcError) -> Exception:
    detail = exc.details() if hasattr(exc, "details") else str(exc)
    code = exc.code() if hasattr(exc, "code") else None
    if code == grpc.StatusCode.NOT_FOUND:
        return CloudDriveNotFoundError(detail)
    if code == grpc.StatusCode.UNAUTHENTICATED:
        return CloudDriveAuthenticationError(detail)
    if code == grpc.StatusCode.PERMISSION_DENIED:
        return CloudDrivePermissionError(detail)
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return CloudDriveRateLimitError(detail)
    if code == grpc.StatusCode.UNAVAILABLE:
        return CloudDriveConnectionError(detail)
    return CloudDriveOperationError(detail)

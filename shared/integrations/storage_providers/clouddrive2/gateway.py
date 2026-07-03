from __future__ import annotations

from typing import Protocol

import grpc

from shared.integrations.storage_providers.clouddrive2.mapper import (
    map_grpc_error,
    map_operation_result,
    map_remote_file,
)
from shared.integrations.storage_providers.clouddrive2.models import (
    OfflineDownloadResult,
    ProviderHealthResult,
    RemoteFile,
    RemoteOperationResult,
)


class StorageProvider(Protocol):
    def health_check(self) -> ProviderHealthResult:
        raise NotImplementedError

    def ensure_directory(self, path: str) -> None:
        raise NotImplementedError

    def submit_offline_download(self, magnet_url: str, target_folder: str) -> OfflineDownloadResult:
        raise NotImplementedError

    def list_files(self, path: str, force_refresh: bool = False) -> list[RemoteFile]:
        raise NotImplementedError

    def find_file(self, path: str) -> RemoteFile | None:
        raise NotImplementedError

    def rename_file(self, source_path: str, new_name: str) -> RemoteOperationResult:
        raise NotImplementedError

    def move_files(self, source_paths: list[str], target_folder: str) -> RemoteOperationResult:
        raise NotImplementedError

    def copy_file(self, source_path: str, dest_folder: str) -> RemoteOperationResult:
        raise NotImplementedError

    def delete_file(self, path: str) -> RemoteOperationResult:
        raise NotImplementedError

    def search_files(
        self,
        search_term: str,
        path: str = "/",
        force_refresh: bool = False,
        fuzzy_match: bool = False,
    ) -> list[RemoteFile]:
        raise NotImplementedError

    def get_original_path(self, path: str) -> str:
        raise NotImplementedError


class CloudDrive2Gateway:
    def __init__(self, client) -> None:
        self.client = client

    def health_check(self) -> ProviderHealthResult:
        try:
            self.client.get_system_info()
            if not getattr(self.client, "token", ""):
                return ProviderHealthResult(reachable=True, authorized=False, error_message="未配置 API Token")
            self.client.list_sub_files("/")
            return ProviderHealthResult(reachable=True, authorized=True, error_message=None)
        except grpc.RpcError as exc:
            return ProviderHealthResult(reachable=False, authorized=False, error_message=str(map_grpc_error(exc)))

    def ensure_directory(self, path: str) -> None:
        self.client.create_folder(path)

    def submit_offline_download(self, magnet_url: str, target_folder: str) -> OfflineDownloadResult:
        try:
            result = self.client.add_offline_download(magnet_url, target_folder)
            paths = list(getattr(result, "resultFilePaths", []))
            return OfflineDownloadResult(success=True, error_message=None, result_paths=paths)
        except grpc.RpcError as exc:
            mapped = map_grpc_error(exc)
            raise mapped from exc

    def list_files(self, path: str, force_refresh: bool = False) -> list[RemoteFile]:
        return [map_remote_file(file_obj) for file_obj in self.client.list_sub_files(path)]

    def find_file(self, path: str) -> RemoteFile | None:
        import posixpath

        parent = posixpath.dirname(path) or "/"
        name = posixpath.basename(path)
        try:
            found = self.client.find_file_by_path(parent, name)
        except grpc.RpcError as exc:
            mapped = map_grpc_error(exc)
            raise mapped from exc
        return map_remote_file(found) if found is not None else None

    def rename_file(self, source_path: str, new_name: str) -> RemoteOperationResult:
        return map_operation_result(self.client.rename_file(source_path, new_name))

    def move_files(self, source_paths: list[str], target_folder: str) -> RemoteOperationResult:
        return map_operation_result(self.client.move_file(source_paths, target_folder))

    def copy_file(self, source_path: str, dest_folder: str) -> RemoteOperationResult:
        """Copy a single file to destination folder."""
        return map_operation_result(self.client.copy_file([source_path], dest_folder))

    def delete_file(self, path: str) -> RemoteOperationResult:
        return map_operation_result(self.client.delete_file(path))

    def search_files(
        self,
        search_term: str,
        path: str = "/",
        force_refresh: bool = False,
        fuzzy_match: bool = False,
    ) -> list[RemoteFile]:
        return [
            map_remote_file(file_obj)
            for file_obj in self.client.search_files(search_term, path, force_refresh, fuzzy_match)
        ]

    def get_original_path(self, path: str) -> str:
        result = self.client.get_original_path(path)
        return str(getattr(result, "result", "") or "")

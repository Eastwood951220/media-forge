"""CloudDrive2 gRPC client.

Thin wrapper around the generated gRPC stubs for CloudDrive2 API.
"""

from __future__ import annotations

import logging
import posixpath
from typing import Any

import grpc
from google.protobuf import empty_pb2

from shared.integrations.storage_providers.clouddrive2.proto import (
    clouddrive_pb2,
    clouddrive_pb2_grpc,
)

logger = logging.getLogger(__name__)


class CloudDriveGrpcClient:
    """gRPC client for CloudDrive2 API."""

    def __init__(self, host: str, token: str = "", timeout: int = 10) -> None:
        """Initialize gRPC client.

        Args:
            host: gRPC server address (e.g. '192.168.0.36:19798').
                  Must NOT include 'http://' prefix.
            token: API token for authenticated calls. Empty = no auth.
            timeout: Default call timeout in seconds.
        """
        self.host = host
        self.token = token
        self.timeout = timeout
        self._channel: grpc.Channel | None = None
        self._stub: clouddrive_pb2_grpc.CloudDriveFileSrvStub | None = None

    def _get_stub(self) -> clouddrive_pb2_grpc.CloudDriveFileSrvStub:
        if self._stub is None:
            self._channel = grpc.insecure_channel(self.host)
            self._stub = clouddrive_pb2_grpc.CloudDriveFileSrvStub(self._channel)
        return self._stub

    def _auth_metadata(self) -> list[tuple[str, str]]:
        """Return gRPC metadata with Bearer token, or empty list."""
        if not self.token:
            return []
        return [("authorization", f"Bearer {self.token}")]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_system_info(self) -> Any:
        """Get system info (no auth required).

        Returns:
            CloudDriveSystemInfo with IsLogin, UserName, SystemReady fields.

        Raises:
            grpc.RpcError: If the call fails (server unreachable, etc.)
        """
        stub = self._get_stub()
        return stub.GetSystemInfo(
            empty_pb2.Empty(),
            metadata=self._auth_metadata(),
            timeout=self.timeout,
        )

    def find_file_by_path(self, parent_path: str, path: str) -> Any | None:
        """Find a file/folder by path (auth required).

        Args:
            parent_path: Parent directory path (e.g. '/' or '/Movies')
            path: File/folder name to find (e.g. 'Movies' or 'video.mp4')

        Returns:
            CloudDriveFile if found, None if not found (NOT_FOUND error).
        """
        stub = self._get_stub()
        request = clouddrive_pb2.FindFileByPathRequest(
            parentPath=parent_path,
            path=path,
        )
        try:
            return stub.FindFileByPath(
                request,
                metadata=self._auth_metadata(),
                timeout=self.timeout,
            )
        except grpc.RpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

    def list_sub_files(self, path: str) -> list[Any]:
        """List files in a directory (auth required, server-streaming).

        Args:
            path: Directory path to list (e.g. '/')

        Returns:
            List of CloudDriveFile objects.
        """
        stub = self._get_stub()
        request = clouddrive_pb2.ListSubFileRequest(
            path=path,
            forceRefresh=False,
        )
        files = []
        for response in stub.GetSubFiles(
            request,
            metadata=self._auth_metadata(),
            timeout=self.timeout,
        ):
            files.extend(response.subFiles)
        return files

    def create_folder(self, path: str) -> Any:
        """Create a folder. Returns CreateFolderResult."""
        parent = posixpath.dirname(path) or "/"
        name = posixpath.basename(path)
        stub = self._get_stub()
        request = clouddrive_pb2.CreateFolderRequest(parentPath=parent, folderName=name)
        return stub.CreateFolder(request, metadata=self._auth_metadata(), timeout=self.timeout)

    def rename_file(self, old_path: str, new_name: str) -> Any:
        """Rename a file. Returns FileOperationResult."""
        stub = self._get_stub()
        request = clouddrive_pb2.RenameFileRequest(theFilePath=old_path, newName=new_name)
        return stub.RenameFile(request, metadata=self._auth_metadata(), timeout=self.timeout)

    def move_file(self, source_paths: list[str], dest_path: str) -> Any:
        """Move files to destination. Returns FileOperationResult."""
        stub = self._get_stub()
        request = clouddrive_pb2.MoveFileRequest(theFilePaths=source_paths, destPath=dest_path)
        return stub.MoveFile(request, metadata=self._auth_metadata(), timeout=self.timeout)

    def copy_file(self, source_paths: list[str], dest_path: str) -> Any:
        """Copy files to destination. Returns FileOperationResult."""
        stub = self._get_stub()
        request = clouddrive_pb2.CopyFileRequest(theFilePaths=source_paths, destPath=dest_path)
        return stub.CopyFile(request, metadata=self._auth_metadata(), timeout=self.timeout)

    def delete_file(self, path: str) -> Any:
        """Delete a file or folder. Returns FileOperationResult."""
        stub = self._get_stub()
        request = clouddrive_pb2.FileRequest(path=path)
        return stub.DeleteFile(request, metadata=self._auth_metadata(), timeout=self.timeout)

    def add_offline_download(self, urls: str, to_folder: str) -> Any:
        """Submit offline download. Returns FileOperationResult."""
        stub = self._get_stub()
        request = clouddrive_pb2.AddOfflineFileRequest(urls=urls, toFolder=to_folder)
        return stub.AddOfflineFiles(request, metadata=self._auth_metadata(), timeout=self.timeout)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> CloudDriveGrpcClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"CloudDriveGrpcClient(host={self.host!r})"

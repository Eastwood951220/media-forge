"""CloudDrive2 storage provider integration."""

from shared.integrations.storage_providers.clouddrive2.exceptions import (
    CloudDriveAuthenticationError,
    CloudDriveConnectionError,
    CloudDriveError,
    CloudDriveNotFoundError,
    CloudDriveOperationError,
    CloudDrivePermissionError,
    CloudDriveRateLimitError,
)
from shared.integrations.storage_providers.clouddrive2.factory import CloudDriveClientFactory
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway, StorageProvider
from shared.integrations.storage_providers.clouddrive2.models import (
    OfflineDownloadResult,
    ProviderHealthResult,
    RemoteFile,
    RemoteOperationResult,
)

__all__ = [
    "CloudDrive2Gateway",
    "CloudDriveClientFactory",
    "StorageProvider",
    "RemoteFile",
    "OfflineDownloadResult",
    "RemoteOperationResult",
    "ProviderHealthResult",
    "CloudDriveError",
    "CloudDriveConnectionError",
    "CloudDriveAuthenticationError",
    "CloudDrivePermissionError",
    "CloudDriveNotFoundError",
    "CloudDriveRateLimitError",
    "CloudDriveOperationError",
]

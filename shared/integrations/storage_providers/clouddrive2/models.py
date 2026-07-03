from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool


@dataclass(frozen=True)
class OfflineDownloadResult:
    success: bool
    error_message: str | None
    result_paths: list[str]


@dataclass(frozen=True)
class RemoteOperationResult:
    success: bool
    error_message: str | None
    result_paths: list[str]


@dataclass(frozen=True)
class ProviderHealthResult:
    reachable: bool
    authorized: bool
    error_message: str | None

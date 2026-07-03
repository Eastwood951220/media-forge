from pydantic import BaseModel, Field


class StorageConfig(BaseModel):
    """CloudDrive2 storage configuration."""

    grpc_host: str = "localhost:9798"
    api_token: str = ""
    request_timeout_seconds: int = Field(default=60, ge=1)
    connect_timeout_seconds: int = Field(default=10, ge=1)

    download_root_folder: str = "/Downloads"
    target_folder: str = "/Movies"
    use_task_subfolder: bool = True
    auto_create_target_folder: bool = True

    operation_delay_min: float = Field(default=0.5, ge=0)
    operation_delay_max: float = Field(default=1.5, ge=0)
    download_poll_interval_min: float = Field(default=5.0, ge=0)
    download_poll_interval_max: float = Field(default=15.0, ge=0)
    retry_delay_min: float = Field(default=10.0, ge=0)
    retry_delay_max: float = Field(default=30.0, ge=0)
    max_step_retries: int = Field(default=3, ge=0)
    download_max_poll_count: int = Field(default=10, ge=1)

    minimum_video_size_mb: int = Field(default=100, ge=0)
    video_extensions: list[str] = Field(
        default_factory=lambda: [".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov"]
    )


class StorageConfigUpdate(BaseModel):
    """Partial update payload for storage configuration."""

    grpc_host: str | None = None
    api_token: str | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=1)
    connect_timeout_seconds: int | None = Field(default=None, ge=1)
    download_root_folder: str | None = None
    target_folder: str | None = None
    use_task_subfolder: bool | None = None
    auto_create_target_folder: bool | None = None
    operation_delay_min: float | None = Field(default=None, ge=0)
    operation_delay_max: float | None = Field(default=None, ge=0)
    download_poll_interval_min: float | None = Field(default=None, ge=0)
    download_poll_interval_max: float | None = Field(default=None, ge=0)
    retry_delay_min: float | None = Field(default=None, ge=0)
    retry_delay_max: float | None = Field(default=None, ge=0)
    max_step_retries: int | None = Field(default=None, ge=0)
    download_max_poll_count: int | None = Field(default=None, ge=1)
    minimum_video_size_mb: int | None = Field(default=None, ge=0)
    video_extensions: list[str] | None = None


class StorageConfigResponse(StorageConfig):
    """Public storage configuration response with masked token."""

    api_token_configured: bool = False


class StorageTestResult(BaseModel):
    """Result of a CloudDrive2 connection test."""

    grpc_reachable: bool = False
    grpc_error: str | None = None
    api_authorized: bool = False
    api_error: str | None = None
    download_root_exists: bool = False
    download_root_error: str | None = None
    target_folder_accessible: bool = False
    target_folder_error: str | None = None

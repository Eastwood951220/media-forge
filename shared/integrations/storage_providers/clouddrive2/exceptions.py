class CloudDriveError(Exception):
    pass


class CloudDriveConnectionError(CloudDriveError):
    pass


class CloudDriveAuthenticationError(CloudDriveError):
    pass


class CloudDrivePermissionError(CloudDriveError):
    pass


class CloudDriveNotFoundError(CloudDriveError):
    pass


class CloudDriveRateLimitError(CloudDriveError):
    pass


class CloudDriveOperationError(CloudDriveError):
    pass

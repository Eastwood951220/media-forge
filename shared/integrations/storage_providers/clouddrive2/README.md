# CloudDrive2 Storage Provider

This package is the only CloudDrive2 integration implementation in the repository.

## Responsibilities

- Create and close gRPC channels.
- Attach CloudDrive2 bearer token metadata.
- Normalize configured host values such as `http://localhost:19798/` to `localhost:19798`.
- Call CloudDrive2 RPC methods through `CloudDriveGrpcClient`.
- Convert protobuf file objects into internal dataclasses.
- Convert gRPC errors into CloudDrive2-specific exceptions.

## Public Boundary

Business code should use:

```python
from shared.integrations.storage_providers.clouddrive2 import (
    CloudDrive2Gateway,
    CloudDriveClientFactory,
)
```

`CloudDriveGrpcClient` and `proto/` are internal to this package. Backend modules must not import protobuf modules or catch `grpc.RpcError` directly.

## Factory Usage

```python
factory = CloudDriveClientFactory()
client = factory.create(
    {
        "grpc_host": "http://localhost:19798/",
        "api_token": "token",
        "request_timeout_seconds": 60,
    }
)
```

## Gateway Usage

```python
gateway = CloudDrive2Gateway(client)
files = gateway.list_files("/Downloads")
```

## Protobuf Regeneration

Regenerate files into `shared/integrations/storage_providers/clouddrive2/proto/` only. Do not recreate the old root `clouddrive/` package.

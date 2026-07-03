from __future__ import annotations

from shared.integrations.storage_providers.clouddrive2.client import CloudDriveGrpcClient


class CloudDriveClientFactory:
    def normalize_host(self, raw_host: str) -> str:
        host = (raw_host or "localhost:9798").strip()
        if host.startswith("http://"):
            host = host[7:]
        elif host.startswith("https://"):
            host = host[8:]
        return host.rstrip("/")

    def create(self, config: dict) -> CloudDriveGrpcClient:
        return CloudDriveGrpcClient(
            host=self.normalize_host(config.get("grpc_host", "localhost:9798")),
            token=config.get("api_token", ""),
            timeout=config.get("request_timeout_seconds", config.get("connect_timeout_seconds", 10)),
        )

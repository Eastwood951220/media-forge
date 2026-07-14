from shared.integrations.storage_providers.clouddrive2.client import CloudDriveGrpcClient
from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway


class EmptySubFilesReply:
    subFiles = []


class CapturingStub:
    def __init__(self) -> None:
        self.requests = []

    def GetSubFiles(self, request, metadata=None, timeout=None):
        self.requests.append(request)
        return [EmptySubFilesReply()]


def test_list_sub_files_passes_force_refresh_to_grpc_request(monkeypatch) -> None:
    stub = CapturingStub()
    client = CloudDriveGrpcClient("localhost:9798", token="token")
    monkeypatch.setattr(client, "_get_stub", lambda: stub)

    client.list_sub_files("/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U", force_refresh=True)

    assert stub.requests[-1].path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U"
    assert stub.requests[-1].forceRefresh is True


def test_gateway_list_files_forwards_force_refresh() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def list_sub_files(self, path, force_refresh=False):
            self.calls.append((path, force_refresh))
            return []

    client = Client()
    gateway = CloudDrive2Gateway(client)

    gateway.list_files("/target", force_refresh=True)

    assert client.calls == [("/target", True)]

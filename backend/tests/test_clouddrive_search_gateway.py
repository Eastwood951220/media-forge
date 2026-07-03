from shared.integrations.storage_providers.clouddrive2.gateway import CloudDrive2Gateway


class FakeClient:
    def __init__(self) -> None:
        self.search_calls = []
        self.original_path_calls = []

    def search_files(self, search_term: str, path: str = "/", force_refresh: bool = False, fuzzy_match: bool = False):
        self.search_calls.append((search_term, path, force_refresh, fuzzy_match))
        return []

    def get_original_path(self, path: str):
        self.original_path_calls.append(path)

        class Result:
            result = "/Movies/ABC-123/ABC-123-C.mp4"

        return Result()


def test_gateway_search_files_delegates_to_client() -> None:
    client = FakeClient()
    gateway = CloudDrive2Gateway(client)

    assert gateway.search_files("ABC-123", "/Downloads", True, True) == []
    assert client.search_calls == [("ABC-123", "/Downloads", True, True)]


def test_gateway_get_original_path_returns_string_result() -> None:
    client = FakeClient()
    gateway = CloudDrive2Gateway(client)

    assert gateway.get_original_path("/Search/ABC-123-C.mp4") == "/Movies/ABC-123/ABC-123-C.mp4"

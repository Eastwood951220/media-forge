import httpx
import pytest

from backend.app.modules.jellyfin.client import JellyfinClient, JellyfinError


def test_client_reads_libraries_and_root_with_header_key() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/Library/VirtualFolders":
            return httpx.Response(200, json=[{"Name": "日本", "ItemId": "lib-1", "Locations": ["/media"]}])
        if request.url.path == "/Users":
            return httpx.Response(200, json=[{"Id": "user-1", "Name": "root"}])
        return httpx.Response(404)

    client = JellyfinClient("http://jellyfin:8096/", "secret-key", transport=httpx.MockTransport(handler))
    assert client.get_virtual_folders()[0]["ItemId"] == "lib-1"
    assert client.get_root_user_id() == "user-1"
    assert all(req.headers["X-Emby-Token"] == "secret-key" for req in requests)
    assert all("secret-key" not in str(req.url) for req in requests)


def test_client_reports_missing_root_and_http_failure_without_key() -> None:
    client = JellyfinClient(
        "http://jellyfin:8096", "secret-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[{"Id": "other", "Name": "admin"}])),
    )
    with pytest.raises(JellyfinError, match="root"):
        client.get_root_user_id()

    denied = JellyfinClient(
        "http://jellyfin:8096", "secret-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text="secret-key denied")),
    )
    with pytest.raises(JellyfinError) as error:
        denied.get_virtual_folders()
    assert "secret-key" not in str(error.value)

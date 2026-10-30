from __future__ import annotations

from typing import Any

import httpx


class JellyfinError(RuntimeError):
    pass


class JellyfinClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not self.base_url or not self.api_key:
            raise JellyfinError("Jellyfin 服务地址或 API Key 未配置")
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=30,
                transport=self.transport,
                headers={"X-Emby-Token": self.api_key},
            ) as client:
                response = client.request(method, path, params=params)
                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise JellyfinError(f"Jellyfin HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise JellyfinError("Jellyfin 请求失败") from exc

    def get_virtual_folders(self) -> list[dict]:
        data = self._request("GET", "/Library/VirtualFolders")
        if not isinstance(data, list):
            raise JellyfinError("Jellyfin 影视库响应格式无效")
        return data

    def get_users(self) -> list[dict]:
        data = self._request("GET", "/Users")
        if not isinstance(data, list):
            raise JellyfinError("Jellyfin 用户响应格式无效")
        return data

    def get_root_user_id(self) -> str:
        for user in self.get_users():
            if isinstance(user, dict) and user.get("Name") == "root" and user.get("Id"):
                return str(user["Id"])
        raise JellyfinError("Jellyfin 中未找到 root 用户")

    def get_items(self, user_id: str, start: int, limit: int) -> dict:
        data = self._request("GET", "/Items", params={
            "userId": user_id,
            "startIndex": start,
            "limit": limit,
            "recursive": "true",
            "includeItemTypes": "Movie",
            "fields": "Path",
            "enableUserData": "true",
        })
        if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
            raise JellyfinError("Jellyfin 影片响应格式无效")
        return data

    def refresh_item(self, item_id: str) -> None:
        self._request("POST", f"/Items/{item_id}/Refresh")

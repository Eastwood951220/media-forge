import json
from pathlib import Path

from scraper.config.settings import COOKIE_DIR


class CookieManager:
    def __init__(self, filename: str):
        self.filepath: Path = COOKIE_DIR / filename

    def load(self) -> dict:
        if not self.filepath.exists():
            return {}

        with self.filepath.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        if isinstance(data, list):
            return {
                item["name"]: item["value"]
                for item in data
                if isinstance(item, dict)
                and "name" in item
                and "value" in item
            }

        return {}

    def save(self, cookies: dict) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        with self.filepath.open("w", encoding="utf-8") as file:
            json.dump(cookies, file, ensure_ascii=False, indent=2)

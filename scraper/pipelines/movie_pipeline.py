from scraper.pipelines.base_pipeline import BasePipeline
from scraper.spiders.javdb.javdb_parser import derive_magnet_tags


class MoviePipeline(BasePipeline):
    def process_items(self, items: list[dict], task_name: str = None) -> list[dict]:
        cleaned: list[dict] = []

        for item in items:
            result = self.process_item(item, task_name=task_name)
            if result is not None:
                cleaned.append(result)

        return cleaned

    def process_item(self, item: dict, task_name: str = None) -> dict | None:
        clean_item = self.clean_item(item, task_name=task_name)

        if not self.is_valid_item(clean_item):
            return None

        return clean_item

    def clean_item(self, item: dict, task_name: str = None) -> dict:
        result = dict(item)

        source_name = item.get("source_name")
        if isinstance(source_name, str):
            result["source_name"] = source_name.strip()

        tags = item.get("tags")
        if isinstance(tags, list) and item.get("has_chinese_sub") and "中文字幕" not in tags:
            result["tags"] = [*tags, "中文字幕"]
        elif "tags" not in item and item.get("has_chinese_sub"):
            result["tags"] = ["中文字幕"]

        if task_name:
            result["source_task_name"] = [task_name]

        # Enrich magnet tags from name
        magnets = item.get("magnets")
        if isinstance(magnets, list):
            enriched_magnets = []
            for magnet in magnets:
                if isinstance(magnet, dict):
                    m = dict(magnet)
                    name = m.get("name") or ""
                    existing = m.get("tags") if isinstance(m.get("tags"), list) else []
                    tags, has_sub = derive_magnet_tags(name, existing)
                    m["tags"] = tags
                    m["has_chinese_sub"] = has_sub
                    enriched_magnets.append(m)
                else:
                    enriched_magnets.append(magnet)
            result["magnets"] = enriched_magnets

        return result

    def is_valid_item(self, item: dict) -> bool:
        return bool(item.get("source_name") or item.get("code") or item.get("source_url"))

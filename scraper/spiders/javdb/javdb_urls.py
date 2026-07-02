from scraper.config.sites import JAVDB_SITE
from scraper.tasks.task_utils import build_page_url

BASE_URL = JAVDB_SITE["base_url"].rstrip("/")


def build_detail_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url

    if not path_or_url.startswith("/"):
        path_or_url = f"/{path_or_url}"

    return f"{BASE_URL}{path_or_url}"


def build_task_page_url(task_final_url: str, page: int) -> str:
    return build_page_url(task_final_url, page)

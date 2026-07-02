import os

JAVDB_SITE = {
    "name": "javdb",
    "base_url": os.getenv("JAVDB_BASE_URL", "https://javdb.com"),
    "cookie_file": "javdb_cookies.json",
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
}

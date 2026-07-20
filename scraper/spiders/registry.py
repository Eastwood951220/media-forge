from scraper.fetchers.scrapling_fetcher import ScraplingFetcher
from scraper.spiders.javbus.javbus_spider import JavbusSpider
from scraper.spiders.javdb.javdb_spider import JavdbSpider


def get_site_spider(source: str, *, fetcher: ScraplingFetcher):
    if source == "javdb":
        return JavdbSpider(fetcher=fetcher)
    if source == "javbus":
        return JavbusSpider(fetcher=fetcher)
    raise ValueError(f"不支持的爬虫来源: {source}")

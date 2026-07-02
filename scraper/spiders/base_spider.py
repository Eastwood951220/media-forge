class BaseSpider:
    name = "base"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch(self, url: str):
        return self.fetcher.get(url)

    def run(self, *args, **kwargs):
        raise NotImplementedError

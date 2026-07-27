class BaseSpider:
    name = "base"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def fetch(self, url: str, **request_options):
        return self.fetcher.get(url, **request_options)

    def run(self, *args, **kwargs):
        raise NotImplementedError

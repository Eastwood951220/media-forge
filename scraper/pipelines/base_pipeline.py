class BasePipeline:
    def process_items(self, items: list[dict]):
        raise NotImplementedError

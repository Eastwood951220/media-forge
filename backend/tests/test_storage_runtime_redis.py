from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState


class FakeRedis:
    def __init__(self) -> None:
        self.lists = {}
        self.values = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        values = self.lists.get(key, [])
        return values.pop(0) if values else None

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)


def test_storage_runtime_queue_and_stop() -> None:
    runtime = StorageRuntimeState(FakeRedis())
    runtime.enqueue_main_task("main-1")

    assert runtime.claim_next_main_task() == "main-1"
    assert runtime.claim_next_main_task() is None

    runtime.request_stop("main-1")
    assert runtime.should_stop("main-1") is True
    runtime.clear_stop("main-1")
    assert runtime.should_stop("main-1") is False


def test_storage_runtime_decodes_byte_task_ids() -> None:
    class BytesRedis(FakeRedis):
        def lpop(self, key):
            value = super().lpop(key)
            return value.encode("utf-8") if value is not None else None

    runtime = StorageRuntimeState(BytesRedis())
    runtime.enqueue_main_task("main-1")

    assert runtime.claim_next_main_task() == "main-1"

from backend.app.modules.crawler.runtime.redis_state import CrawlerRuntimeState


class FakeRedis:
    def __init__(self) -> None:
        self.values = {}
        self.lists = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        values = self.lists.get(key, [])
        return values.pop(0) if values else None

    def llen(self, key):
        return len(self.lists.get(key, []))

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)

    def keys(self, pattern):
        prefix = pattern.removesuffix("*")
        return [key for key in [*self.values, *self.lists] if key.startswith(prefix)]


def test_enqueue_claim_and_queue_status() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())

    runtime.enqueue_run("run-1")

    assert runtime.queue_status()["queue_size"] == 1
    assert runtime.claim_next_run() == "run-1"
    assert runtime.queue_status()["queue_size"] == 0


def test_stop_signal_and_cleanup() -> None:
    redis = FakeRedis()
    runtime = CrawlerRuntimeState(redis)

    runtime.set_current_run("run-1")
    runtime.request_stop("run-1")
    runtime.write_progress("run-1", {"total": 3, "finished": 1})

    assert runtime.is_stop_requested("run-1") is True
    assert runtime.read_progress("run-1") == {"total": 3, "finished": 1}

    runtime.cleanup_runtime()

    assert runtime.queue_status() == {
        "queue_size": 0,
        "is_running": False,
        "current_run_id": None,
        "stop_requested": False,
    }

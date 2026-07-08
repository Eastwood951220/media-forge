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

    def lrem(self, key, count, value):
        values = self.lists.get(key, [])
        original_len = len(values)
        if count == 0:
            self.lists[key] = [item for item in values if item != value]
        elif count > 0:
            removed = 0
            next_values = []
            for item in values:
                if item == value and removed < count:
                    removed += 1
                    continue
                next_values.append(item)
            self.lists[key] = next_values
        else:
            removed = 0
            next_values = []
            for item in reversed(values):
                if item == value and removed < abs(count):
                    removed += 1
                    continue
                next_values.append(item)
            self.lists[key] = list(reversed(next_values))
        return original_len - len(self.lists.get(key, []))


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


def test_clear_stop_signal() -> None:
    redis = FakeRedis()
    runtime = CrawlerRuntimeState(redis)

    runtime.request_stop("run-1")
    assert runtime.is_stop_requested("run-1") is True

    runtime.clear_stop("run-1")

    assert runtime.is_stop_requested("run-1") is False
    assert runtime.queue_status()["stop_requested"] is False


def test_remove_queued_run_removes_all_matching_queue_entries() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.enqueue_run("run-1")
    runtime.enqueue_run("run-2")
    runtime.enqueue_run("run-1")

    assert runtime.remove_queued_run("run-1") == 2

    assert runtime.queue_status()["queue_size"] == 1
    assert runtime.claim_next_run() == "run-2"
    assert runtime.claim_next_run() is None


def test_purge_run_clears_queue_stop_progress_and_matching_current() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.enqueue_run("run-1")
    runtime.enqueue_run("run-2")
    runtime.set_current_run("run-1")
    runtime.request_stop("run-1")
    runtime.write_progress("run-1", {"total": 9})

    runtime.purge_run("run-1")

    assert runtime.is_stop_requested("run-1") is False
    assert runtime.read_progress("run-1") == {}
    assert runtime.queue_status() == {
        "queue_size": 1,
        "is_running": False,
        "current_run_id": None,
        "stop_requested": False,
    }
    assert runtime.claim_next_run() == "run-2"


def test_purge_run_keeps_other_current_run() -> None:
    runtime = CrawlerRuntimeState(FakeRedis())
    runtime.set_current_run("run-2")
    runtime.request_stop("run-1")

    runtime.purge_run("run-1")

    assert runtime.queue_status()["current_run_id"] == "run-2"

import json
from typing import Any


class CrawlerRuntimeState:
    PREFIX = "media-forge:crawler:"
    QUEUE_KEY = f"{PREFIX}queue"
    CURRENT_KEY = f"{PREFIX}current_run_id"

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    def _stop_key(self, run_id: str) -> str:
        return f"{self.PREFIX}stop:{run_id}"

    def _progress_key(self, run_id: str) -> str:
        return f"{self.PREFIX}progress:{run_id}"

    def enqueue_run(self, run_id: str) -> None:
        self.redis.rpush(self.QUEUE_KEY, run_id)

    def claim_next_run(self) -> str | None:
        value = self.redis.lpop(self.QUEUE_KEY)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def set_current_run(self, run_id: str | None) -> None:
        if run_id is None:
            self.redis.delete(self.CURRENT_KEY)
            return
        self.redis.set(self.CURRENT_KEY, run_id)

    def request_stop(self, run_id: str) -> None:
        self.redis.set(self._stop_key(run_id), "1")

    def is_stop_requested(self, run_id: str) -> bool:
        return self.redis.get(self._stop_key(run_id)) is not None

    def write_progress(self, run_id: str, progress: dict[str, Any]) -> None:
        self.redis.set(self._progress_key(run_id), json.dumps(progress))

    def read_progress(self, run_id: str) -> dict[str, Any]:
        raw = self.redis.get(self._progress_key(run_id))
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def cleanup_runtime(self) -> None:
        keys = list(self.redis.keys(f"{self.PREFIX}*"))
        if keys:
            self.redis.delete(*keys)

    def queue_status(self) -> dict[str, Any]:
        current = self.redis.get(self.CURRENT_KEY)
        current_run_id = current.decode() if isinstance(current, bytes) else current
        return {
            "queue_size": self.redis.llen(self.QUEUE_KEY),
            "is_running": current_run_id is not None,
            "current_run_id": current_run_id,
            "stop_requested": bool(current_run_id and self.is_stop_requested(str(current_run_id))),
        }

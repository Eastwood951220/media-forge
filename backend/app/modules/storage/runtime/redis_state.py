class StorageRuntimeState:
    QUEUE_KEY = "storage:main_queue"
    CURRENT_KEY = "storage:current_main_task"
    STOP_PREFIX = "storage:stop:"

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    def enqueue_main_task(self, task_id: str) -> None:
        self.redis.rpush(self.QUEUE_KEY, task_id)

    def claim_next_main_task(self) -> str | None:
        value = self.redis.lpop(self.QUEUE_KEY)
        if value is None:
            return None
        task_id = str(value)
        self.redis.set(self.CURRENT_KEY, task_id)
        return task_id

    def set_current_main_task(self, task_id: str | None) -> None:
        if task_id is None:
            self.redis.delete(self.CURRENT_KEY)
        else:
            self.redis.set(self.CURRENT_KEY, task_id)

    def request_stop(self, task_id: str) -> None:
        self.redis.set(f"{self.STOP_PREFIX}{task_id}", "1")

    def should_stop(self, task_id: str) -> bool:
        return self.redis.get(f"{self.STOP_PREFIX}{task_id}") == "1"

    def clear_stop(self, task_id: str) -> None:
        self.redis.delete(f"{self.STOP_PREFIX}{task_id}")

    def cleanup_runtime(self) -> None:
        self.redis.delete(self.QUEUE_KEY, self.CURRENT_KEY)

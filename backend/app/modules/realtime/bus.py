from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock

from backend.app.modules.realtime.schemas import RealtimeEvent, make_realtime_event


class RealtimeEventBus:
    def __init__(self, queue_size: int = 500) -> None:
        self.queue_size = queue_size
        self._lock = Lock()
        self._subscribers: dict[str, set[Queue[RealtimeEvent]]] = {}

    def subscribe(self, owner_id: str) -> Queue[RealtimeEvent]:
        queue: Queue[RealtimeEvent] = Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers.setdefault(owner_id, set()).add(queue)
        return queue

    def unsubscribe(self, owner_id: str, queue: Queue[RealtimeEvent]) -> None:
        with self._lock:
            queues = self._subscribers.get(owner_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(owner_id, None)

    def publish(self, event: RealtimeEvent) -> int:
        with self._lock:
            queues = list(self._subscribers.get(event.owner_id, set()))

        delivered = 0
        for queue in queues:
            if self._put_or_resync(queue, event):
                delivered += 1
        return delivered

    def _put_or_resync(self, queue: Queue[RealtimeEvent], event: RealtimeEvent) -> bool:
        try:
            queue.put_nowait(event)
            return True
        except Full:
            self._clear_queue(queue)
            queue.put_nowait(
                make_realtime_event(
                    event="system.resync_required",
                    scope="system",
                    owner_id=event.owner_id,
                    resource_id=event.resource_id,
                    payload={"reason": "queue_overflow"},
                )
            )
            return True

    @staticmethod
    def _clear_queue(queue: Queue[RealtimeEvent]) -> None:
        while True:
            try:
                queue.get_nowait()
            except Empty:
                return


event_bus = RealtimeEventBus()

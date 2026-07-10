from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Any

from backend.app.modules.realtime.schemas import (
    RealtimeEvent,
    make_realtime_event,
    realtime_event_from_json,
    realtime_event_to_json,
)

logger = logging.getLogger(__name__)


@dataclass
class _OwnerListener:
    thread: threading.Thread
    stop_event: threading.Event
    ref_count: int = 0


class RealtimeEventBus:
    CHANNEL_PREFIX = "media-forge:realtime:owner:"

    def __init__(
        self,
        queue_size: int = 500,
        redis_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.queue_size = queue_size
        self._origin_id = uuid.uuid4().hex
        self._redis_client_factory = redis_client_factory
        self._lock = threading.RLock()
        self._subscribers: dict[str, set[Queue[RealtimeEvent]]] = {}
        self._listeners: dict[str, _OwnerListener] = {}

    def configure_redis(self, redis_client_factory: Callable[[], Any]) -> None:
        with self._lock:
            self._redis_client_factory = redis_client_factory

    def subscribe(self, owner_id: str) -> Queue[RealtimeEvent]:
        queue: Queue[RealtimeEvent] = Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers.setdefault(owner_id, set()).add(queue)
            self._ensure_owner_listener_locked(owner_id)
        return queue

    def unsubscribe(self, owner_id: str, queue: Queue[RealtimeEvent]) -> None:
        with self._lock:
            queues = self._subscribers.get(owner_id)
            if queues:
                queues.discard(queue)
                if not queues:
                    self._subscribers.pop(owner_id, None)
            self._release_owner_listener_locked(owner_id)

    def publish(self, event: RealtimeEvent) -> int:
        delivered = self._publish_local(event)
        self._publish_redis(event)
        return delivered

    def close(self) -> None:
        with self._lock:
            listeners = list(self._listeners.values())
            self._listeners.clear()
            self._subscribers.clear()
        for listener in listeners:
            listener.stop_event.set()

    def _publish_local(self, event: RealtimeEvent) -> int:
        with self._lock:
            queues = list(self._subscribers.get(event.owner_id, set()))

        delivered = 0
        for queue in queues:
            if self._put_or_resync(queue, event):
                delivered += 1
        return delivered

    def _publish_redis(self, event: RealtimeEvent) -> None:
        redis_client = self._redis_client()
        if redis_client is None:
            return
        envelope = {"origin_id": self._origin_id, "event": realtime_event_to_json(event)}
        try:
            redis_client.publish(self._channel(event.owner_id), json.dumps(envelope, ensure_ascii=False))
        except Exception:
            logger.warning(
                "Failed to publish realtime event to Redis: event=%s owner_id=%s resource_id=%s",
                event.event,
                event.owner_id,
                event.resource_id,
                exc_info=True,
            )

    def _ensure_owner_listener_locked(self, owner_id: str) -> None:
        if self._redis_client_factory is None:
            return
        listener = self._listeners.get(owner_id)
        if listener is not None:
            listener.ref_count += 1
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._listen_owner,
            args=(owner_id, stop_event),
            daemon=True,
        )
        self._listeners[owner_id] = _OwnerListener(thread=thread, stop_event=stop_event, ref_count=1)
        thread.start()

    def _release_owner_listener_locked(self, owner_id: str) -> None:
        listener = self._listeners.get(owner_id)
        if listener is None:
            return
        listener.ref_count -= 1
        if listener.ref_count > 0:
            return
        listener.stop_event.set()
        self._listeners.pop(owner_id, None)

    def _listen_owner(self, owner_id: str, stop_event: threading.Event) -> None:
        redis_client = self._redis_client()
        if redis_client is None:
            return
        pubsub = redis_client.pubsub()
        try:
            pubsub.subscribe(self._channel(owner_id))
            for message in pubsub.listen():
                if stop_event.is_set():
                    return
                if message.get("type") != "message":
                    continue
                self._handle_redis_message(owner_id, message.get("data"))
        except Exception:
            logger.warning("Realtime Redis listener stopped for owner_id=%s", owner_id, exc_info=True)
            self._publish_local(make_realtime_event(
                event="system.resync_required",
                scope="system",
                owner_id=owner_id,
                payload={"reason": "redis_listener_error"},
            ))
        finally:
            try:
                pubsub.close()
            except Exception:
                logger.debug("Failed to close Redis pubsub", exc_info=True)

    def _handle_redis_message(self, owner_id: str, data: str | bytes) -> None:
        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            envelope = json.loads(data)
            if envelope.get("origin_id") == self._origin_id:
                return
            event = realtime_event_from_json(envelope["event"])
        except Exception:
            logger.warning("Malformed realtime Redis event for owner_id=%s", owner_id, exc_info=True)
            self._publish_local(make_realtime_event(
                event="system.resync_required",
                scope="system",
                owner_id=owner_id,
                payload={"reason": "malformed_event"},
            ))
            return
        self._publish_local(event)

    def _redis_client(self):
        if self._redis_client_factory is None:
            return None
        try:
            return self._redis_client_factory()
        except Exception:
            logger.warning("Realtime Redis client unavailable", exc_info=True)
            return None

    @classmethod
    def _channel(cls, owner_id: str) -> str:
        return f"{cls.CHANNEL_PREFIX}{owner_id}"

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

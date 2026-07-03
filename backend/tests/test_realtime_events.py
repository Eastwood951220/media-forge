import json
from datetime import UTC

from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.modules.realtime.bus import RealtimeEventBus
from backend.app.modules.realtime.schemas import make_realtime_event
from backend.app.modules.realtime.sse import format_sse_event


def test_make_realtime_event_fills_required_metadata() -> None:
    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-1",
        resource_id="run-1",
        payload={"status": "running"},
    )

    assert event.event == "crawler.run.updated"
    assert event.scope == "crawler.run"
    assert event.owner_id == "user-1"
    assert event.resource_id == "run-1"
    assert event.payload == {"status": "running"}
    assert event.id
    assert event.created_at.tzinfo is not None
    assert event.created_at.utcoffset() == UTC.utcoffset(event.created_at)


def test_format_sse_event_outputs_standard_event_frame() -> None:
    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-1",
        resource_id="run-1",
        payload={"status": "running"},
    )

    frame = format_sse_event(event)

    assert frame.startswith(f"id: {event.id}\n")
    assert "\nevent: crawler.run.updated\n" in frame
    assert frame.endswith("\n\n")
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    data = json.loads(data_line.removeprefix("data: "))
    assert data["event"] == "crawler.run.updated"
    assert data["payload"] == {"status": "running"}


def test_realtime_bus_routes_events_by_owner() -> None:
    bus = RealtimeEventBus(queue_size=10)
    user_a_queue = bus.subscribe("user-a")
    user_b_queue = bus.subscribe("user-b")

    event = make_realtime_event(
        event="crawler.run.updated",
        scope="crawler.run",
        owner_id="user-a",
        resource_id="run-1",
        payload={"status": "running"},
    )
    delivered = bus.publish(event)

    assert delivered == 1
    assert user_a_queue.get_nowait().id == event.id
    assert user_b_queue.empty()

    bus.unsubscribe("user-a", user_a_queue)
    bus.unsubscribe("user-b", user_b_queue)


def test_realtime_bus_emits_resync_when_queue_is_full() -> None:
    bus = RealtimeEventBus(queue_size=1)
    queue = bus.subscribe("user-a")

    bus.publish(make_realtime_event(event="one", scope="test", owner_id="user-a", payload={}))
    bus.publish(make_realtime_event(event="two", scope="test", owner_id="user-a", payload={}))

    event = queue.get_nowait()
    assert event.event == "system.resync_required"
    assert event.scope == "system"
    assert event.owner_id == "user-a"

    bus.unsubscribe("user-a", queue)


def test_event_stream_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/events/stream")

    assert response.status_code == 401


def test_event_stream_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/api/events/stream?token=bad-token")

    assert response.status_code == 401


def test_event_stream_endpoint_exists_and_requires_auth(client: TestClient) -> None:
    """Verify the SSE endpoint exists and rejects bad tokens."""
    response = client.get("/api/events/stream?token=bad")
    assert response.status_code == 401

"""Tests for crawler SSE event streaming system."""

import asyncio
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.modules.crawler.events.bus import EventBus
from backend.app.modules.crawler.events.schemas import (
    CrawlerEvent,
    RunLogEvent,
    RunProgressEvent,
    RunStatusEvent,
    TaskStatusEvent,
)


# ---- Event Bus Tests ----


class TestEventBus:
    """Tests for the EventBus singleton."""

    def test_subscribe_returns_client_id_and_queue(self):
        bus = EventBus()
        client_id, queue = bus.subscribe()

        assert client_id is not None
        assert len(client_id) == 12
        assert queue is not None

        bus.unsubscribe(client_id, queue)

    def test_subscribe_with_custom_client_id(self):
        bus = EventBus()
        client_id, queue = bus.subscribe("custom-id")

        assert client_id == "custom-id"

        bus.unsubscribe(client_id, queue)

    def test_publish_delivers_to_subscribed_queues(self):
        bus = EventBus()
        client_id, queue = bus.subscribe()

        event = RunStatusEvent(
            run_id="run-1",
            status="running",
            task_name="Test Task",
        )
        bus.publish(event)

        assert not queue.empty()
        received = queue.get_nowait()
        assert received.run_id == "run-1"
        assert received.status == "running"

        bus.unsubscribe(client_id, queue)

    def test_publish_does_not_deliver_after_unsubscribe(self):
        bus = EventBus()
        client_id, queue = bus.subscribe()

        # Unsubscribe first
        bus.unsubscribe(client_id, queue)

        # Publish after unsubscribe - should not be in queue
        event = RunStatusEvent(run_id="run-1", status="running")
        bus.publish(event)

        assert queue.empty()

    def test_publish_fans_out_to_multiple_clients(self):
        bus = EventBus()
        client_a, queue_a = bus.subscribe()
        client_b, queue_b = bus.subscribe()

        event = RunStatusEvent(run_id="run-1", status="running")
        bus.publish(event)

        assert not queue_a.empty()
        assert not queue_b.empty()

        bus.unsubscribe(client_a, queue_a)
        bus.unsubscribe(client_b, queue_b)

    def test_unsubscribe_is_safe_to_call_multiple_times(self):
        bus = EventBus()
        client_id, queue = bus.subscribe()

        bus.unsubscribe(client_id, queue)
        bus.unsubscribe(client_id, queue)  # Should not raise

    def test_subscriber_count_returns_total_queues(self):
        bus = EventBus()
        client_a, queue_a = bus.subscribe()
        client_b, queue_b = bus.subscribe()

        assert bus.subscriber_count == 2

        bus.unsubscribe(client_a, queue_a)
        assert bus.subscriber_count == 1

        bus.unsubscribe(client_b, queue_b)
        assert bus.subscriber_count == 0


# ---- Event Schema Tests ----


class TestCrawlerEventSchemas:
    """Tests for crawler event Pydantic schemas."""

    def test_run_status_event_has_correct_type(self):
        event = RunStatusEvent(run_id="run-1", status="running")
        assert event.type == "run:status"

    def test_run_progress_event_has_correct_type(self):
        event = RunProgressEvent(run_id="run-1", total=10, saved=5)
        assert event.type == "run:progress"

    def test_run_log_event_has_correct_type(self):
        event = RunLogEvent(run_id="run-1", message="Test log")
        assert event.type == "run:log"

    def test_task_status_event_has_correct_type(self):
        event = TaskStatusEvent(run_id="run-1", status="saved")
        assert event.type == "task:status"

    def test_events_have_timestamp(self):
        event = RunStatusEvent(run_id="run-1", status="running")
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)

    def test_run_status_event_serializes_to_json(self):
        event = RunStatusEvent(
            run_id="run-1",
            status="running",
            task_name="Test Task",
            error=None,
        )
        data = json.loads(event.model_dump_json())

        assert data["type"] == "run:status"
        assert data["run_id"] == "run-1"
        assert data["status"] == "running"
        assert data["task_name"] == "Test Task"
        assert "timestamp" in data

    def test_run_progress_event_serializes_with_all_fields(self):
        event = RunProgressEvent(
            run_id="run-1",
            total=100,
            saved=80,
            failed=5,
            skipped=10,
            save_failed=5,
        )
        data = json.loads(event.model_dump_json())

        assert data["total"] == 100
        assert data["saved"] == 80
        assert data["failed"] == 5
        assert data["skipped"] == 10
        assert data["save_failed"] == 5

    def test_run_log_event_includes_context(self):
        event = RunLogEvent(
            run_id="run-1",
            level="INFO",
            message="入库成功",
            context={"code": "AAA-001"},
        )
        data = json.loads(event.model_dump_json())

        assert data["level"] == "INFO"
        assert data["context"]["code"] == "AAA-001"

    def test_discriminated_union_deserializes_correctly(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(CrawlerEvent)

        # Test RunStatusEvent
        json_str = '{"type":"run:status","timestamp":"2026-07-03T00:00:00","run_id":"run-1","status":"running"}'
        event = adapter.validate_json(json_str)
        assert isinstance(event, RunStatusEvent)

        # Test RunProgressEvent
        json_str = '{"type":"run:progress","timestamp":"2026-07-03T00:00:00","run_id":"run-1","total":10}'
        event = adapter.validate_json(json_str)
        assert isinstance(event, RunProgressEvent)

        # Test RunLogEvent
        json_str = '{"type":"run:log","timestamp":"2026-07-03T00:00:00","run_id":"run-1","message":"test"}'
        event = adapter.validate_json(json_str)
        assert isinstance(event, RunLogEvent)

        # Test TaskStatusEvent
        json_str = '{"type":"task:status","timestamp":"2026-07-03T00:00:00","run_id":"run-1","status":"saved"}'
        event = adapter.validate_json(json_str)
        assert isinstance(event, TaskStatusEvent)


# ---- SSE Router Tests ----


class TestSSERouter:
    """Tests for the SSE streaming endpoint."""

    def test_stream_rejects_missing_token(self, client: TestClient):
        response = client.get("/api/crawler/stream")
        assert response.status_code == 422  # FastAPI validation error for missing required param

    def test_stream_rejects_invalid_token(self, client: TestClient):
        response = client.get("/api/crawler/stream?token=invalid-token")
        assert response.status_code == 401

    def test_stream_endpoint_exists_and_requires_auth(self, client: TestClient):
        """Verify the SSE endpoint exists and rejects bad tokens."""
        response = client.get("/api/crawler/stream?token=bad")
        assert response.status_code == 401

    def test_stream_endpoint_is_marked_deprecated(self, client: TestClient):
        schema = client.get("/openapi.json").json()

        operation = schema["paths"]["/api/crawler/stream"]["get"]

        assert operation["deprecated"] is True

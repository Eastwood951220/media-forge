"""Protocol, timing, and retry constants for Chrome Agent dispatch."""

AGENT_PROTOCOL_VERSION: int = 2
"""Current WebSocket protocol version the backend speaks."""

AGENT_MINIMUM_PROTOCOL_VERSION: int = 2
"""Lowest protocol version the extension must support to connect."""

AGENT_REQUIRED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "task_events",
        "attempt_guard",
        "execution_deadline",
    }
)
"""Capabilities the extension must advertise to be considered compatible."""

AGENT_HEARTBEAT_INTERVAL_SECONDS: int = 20
"""How often the extension should send a heartbeat (seconds)."""

AGENT_HEARTBEAT_FRESH_SECONDS: int = 45
"""How old the last heartbeat can be before the agent is considered stale."""

AGENT_TASK_POLL_INTERVAL_MS: int = 1000
"""How often the extension polls for a new task when idle (milliseconds)."""

AGENT_MAX_ATTEMPTS: int = 3
"""Maximum number of times a work item may be attempted before being discarded."""

AGENT_EVENT_RETENTION_DAYS: int = 7
"""How many days operational events are retained before automatic cleanup."""
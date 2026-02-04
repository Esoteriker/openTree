from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.common.config import settings

try:
    from redis import Redis
except Exception:  # pragma: no cover - optional dependency fallback
    Redis = None  # type: ignore[assignment]


@dataclass
class EventEnvelope:
    message_id: str
    topic: str
    key: str | None
    payload: dict[str, Any]


class EventBus:
    def publish(self, topic: str, payload: dict[str, Any], key: str | None = None) -> str:
        raise NotImplementedError

    def consume(
        self,
        topic: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 20,
        block_ms: int = 1000,
    ) -> list[EventEnvelope]:
        raise NotImplementedError

    def ack(self, topic: str, consumer_group: str, messages: list[EventEnvelope]) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._topics: dict[str, deque[EventEnvelope]] = defaultdict(deque)
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: dict[str, Any], key: str | None = None) -> str:
        message_id = uuid4().hex
        envelope = EventEnvelope(message_id=message_id, topic=topic, key=key, payload=payload)
        with self._lock:
            self._topics[topic].append(envelope)
        return message_id

    def consume(
        self,
        topic: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 20,
        block_ms: int = 1000,
    ) -> list[EventEnvelope]:
        del consumer_group, consumer_name
        out: list[EventEnvelope] = []
        with self._lock:
            queue = self._topics[topic]
            for _ in range(min(count, len(queue))):
                out.append(queue.popleft())
        if not out and block_ms > 0:
            time.sleep(block_ms / 1000.0)
        return out

    def ack(self, topic: str, consumer_group: str, messages: list[EventEnvelope]) -> None:
        del topic, consumer_group, messages
        return None


class RedisStreamEventBus(EventBus):
    def __init__(self, redis_url: str, stream_prefix: str) -> None:
        if Redis is None:
            raise RuntimeError("redis package is required for RedisStreamEventBus")
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._stream_prefix = stream_prefix
        self._group_ready: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def _stream_name(self, topic: str) -> str:
        return f"{self._stream_prefix}:{topic}"

    def _ensure_group(self, stream_name: str, consumer_group: str) -> None:
        key = (stream_name, consumer_group)
        with self._lock:
            if key in self._group_ready:
                return
            try:
                self._redis.xgroup_create(stream_name, consumer_group, id="$", mkstream=True)
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            self._group_ready.add(key)

    def publish(self, topic: str, payload: dict[str, Any], key: str | None = None) -> str:
        stream_name = self._stream_name(topic)
        body = {"payload": json.dumps(payload)}
        if key:
            body["key"] = key
        return str(self._redis.xadd(stream_name, fields=body))

    def consume(
        self,
        topic: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 20,
        block_ms: int = 1000,
    ) -> list[EventEnvelope]:
        stream_name = self._stream_name(topic)
        self._ensure_group(stream_name, consumer_group)
        rows = self._redis.xreadgroup(
            groupname=consumer_group,
            consumername=consumer_name,
            streams={stream_name: ">"},
            count=count,
            block=block_ms,
        )

        out: list[EventEnvelope] = []
        for _, entries in rows:
            for message_id, fields in entries:
                payload = json.loads(fields.get("payload", "{}"))
                key = fields.get("key")
                out.append(EventEnvelope(message_id=message_id, topic=topic, key=key, payload=payload))
        return out

    def ack(self, topic: str, consumer_group: str, messages: list[EventEnvelope]) -> None:
        if not messages:
            return
        stream_name = self._stream_name(topic)
        self._redis.xack(stream_name, consumer_group, *[m.message_id for m in messages])


def build_event_bus() -> EventBus:
    if settings.event_bus_backend.lower() == "redis":
        return RedisStreamEventBus(redis_url=settings.redis_url, stream_prefix=settings.redis_stream_prefix)
    return InMemoryEventBus()

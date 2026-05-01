"""
EventBus — Redis Streams-backed internal event bus.

Events are written to a per-game Redis Stream (`sim:events:{game_id}`).
The tick engine appends events; the WebSocket broadcaster reads and fans them out.

Redis Streams give us:
  - Durable, ordered, replay-capable event log within a session
  - O(1) append (XADD)
  - O(N) range read (XRANGE / XREAD) where N = events per tick (small)

Stream entries are auto-trimmed to the last 10,000 events per game to cap memory.
"""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from .models import RKeys, SimEvent, SimEventType


_STREAM_MAXLEN = 10_000  # events retained per game


class EventBus:
    """
    Thin wrapper around Redis Streams for simulation events.

    Usage in tick engine:
        bus = EventBus(redis)
        await bus.publish(game_id, SimEvent(...))

    Usage in broadcaster:
        events = await bus.read_since(game_id, last_id="$")
    """

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def publish(self, game_id: str, event: SimEvent) -> str:
        """Append event to game stream.  Returns the Redis stream entry ID."""
        payload: dict[str, str] = {
            "type":        event.type,
            "tick":        str(event.tick),
            "platform_id": event.platform_id or "",
            "narrative":   event.narrative,
            "data":        json.dumps(event.data),
        }
        entry_id: str = await self._r.xadd(
            RKeys.event_stream(game_id),
            payload,
            maxlen=_STREAM_MAXLEN,
            approximate=True,
        )
        return entry_id

    async def publish_many(self, game_id: str, events: list[SimEvent]) -> None:
        """Batch-publish a list of events via a single Redis pipeline."""
        if not events:
            return
        pipe = self._r.pipeline(transaction=False)
        for ev in events:
            payload: dict[str, str] = {
                "type":        ev.type,
                "tick":        str(ev.tick),
                "platform_id": ev.platform_id or "",
                "narrative":   ev.narrative,
                "data":        json.dumps(ev.data),
            }
            pipe.xadd(
                RKeys.event_stream(game_id),
                payload,
                maxlen=_STREAM_MAXLEN,
                approximate=True,
            )
        await pipe.execute()

    async def read_since(
        self, game_id: str, last_id: str = "0-0", count: int = 500
    ) -> list[tuple[str, SimEvent]]:
        """
        Read events from the stream since `last_id`.

        Returns list of (entry_id, SimEvent) pairs.  Caller should store the
        last returned entry_id and pass it next call.

        Pass last_id="$" to start reading from the current end (new events only).
        """
        entries: list[Any] = await self._r.xread(
            {RKeys.event_stream(game_id): last_id},
            count=count,
            block=0,
        )
        if not entries:
            return []

        result: list[tuple[str, SimEvent]] = []
        for _stream, messages in entries:
            for entry_id, fields in messages:
                try:
                    ev = SimEvent(
                        type=SimEventType(fields["type"]),
                        tick=int(fields["tick"]),
                        platform_id=fields["platform_id"] or None,
                        narrative=fields.get("narrative", ""),
                        data=json.loads(fields.get("data", "{}")),
                        game_id=game_id,
                    )
                    result.append((entry_id, ev))
                except (KeyError, ValueError):
                    pass  # malformed entry — skip
        return result

    async def trim_game(self, game_id: str) -> None:
        """Remove the event stream when a game is deleted/reset."""
        await self._r.delete(RKeys.event_stream(game_id))

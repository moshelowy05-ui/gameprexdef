"""
OrderQueue — Redis Sorted Set-backed command queue.

Key: sim:orders:{game_id}
Score: priority * 1_000_000 + submission_tick  (lower = higher priority, earlier)
Member: JSON-serialised PlatformOrder

This gives us:
  - Deterministic order resolution every tick (ZRANGEBYSCORE always returns same order)
  - O(log N) insert, O(K log N) read of top-K orders
  - Per-platform order replacement: ZREM old + ZADD new is atomic via pipeline

Order Resolution Order (enforced by score):
  1. NCA_OVERRIDE  (priority 0)   — nuclear / critical authority commands
  2. EMERGENCY     (priority 100) — evasion, emergency RTB
  3. MISSION       (priority 200) — mission-assigned waypoints
  4. LOGISTICS     (priority 300) — fuel/maintenance RTB
  5. ROUTINE       (priority 400) — normal ops
"""
from __future__ import annotations

import json
import uuid

from redis.asyncio import Redis

from .models import OrderPriority, OrderType, PlatformOrder, RKeys


def _score(priority: int, tick: int) -> float:
    """Lower score = processed first."""
    return priority * 1_000_000 + tick


class OrderQueue:
    """
    Thread-safe (asyncio-safe) Redis-backed order queue.

    One queue per game, shared by all platforms in that game.
    Each platform may have at most one queued order per priority tier
    (enforced by using platform_id + priority as a logical key).
    """

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def submit(self, order: PlatformOrder) -> None:
        """Enqueue an order.  Replaces any existing order for the same
        platform at the same priority tier atomically."""
        key = RKeys.order_queue(order.game_id)
        serialised = order.model_dump_json()

        # Remove any existing order for same platform+priority (deterministic replacement)
        # We scan for member matching platform_id + priority prefix — this is O(N) on
        # the queue size, but queues are expected to be small (< 1000 entries).
        existing: list[str] = await self._r.zrange(key, 0, -1)
        pipe = self._r.pipeline(transaction=True)
        for raw in existing:
            try:
                d = json.loads(raw)
                if d.get("platform_id") == order.platform_id and d.get("priority") == order.priority:
                    pipe.zrem(key, raw)
            except (json.JSONDecodeError, KeyError):
                pass
        pipe.zadd(key, {serialised: _score(order.priority, order.submission_tick)})
        await pipe.execute()

    async def submit_many(self, orders: list[PlatformOrder]) -> None:
        """Batch submit. No deduplication — caller must ensure no conflicts."""
        if not orders:
            return
        pipe = self._r.pipeline(transaction=False)
        for order in orders:
            key = RKeys.order_queue(order.game_id)
            pipe.zadd(
                key,
                {order.model_dump_json(): _score(order.priority, order.submission_tick)},
            )
        await pipe.execute()

    async def pop_all(self, game_id: str) -> list[PlatformOrder]:
        """
        Atomically fetch ALL pending orders for this tick and remove them.

        Returns orders sorted by score (priority ASC, then tick ASC).
        Time complexity: O(N) where N = number of pending orders.
        """
        key = RKeys.order_queue(game_id)
        # ZPOPMIN returns (member, score) pairs sorted by score ascending
        raw_pairs: list[tuple[str, float]] = await self._r.zpopmin(key, count=10_000)
        orders: list[PlatformOrder] = []
        for raw, _score in raw_pairs:
            try:
                orders.append(PlatformOrder.model_validate_json(raw))
            except Exception:
                pass  # malformed entry — discard
        return orders

    async def peek(self, game_id: str, count: int = 100) -> list[PlatformOrder]:
        """Read top-N orders without removing them (for inspection/debug)."""
        key = RKeys.order_queue(game_id)
        raw_pairs: list[tuple[str, float]] = await self._r.zrange(
            key, 0, count - 1, withscores=True
        )
        orders = []
        for raw, _ in raw_pairs:
            try:
                orders.append(PlatformOrder.model_validate_json(raw))
            except Exception:
                pass
        return orders

    async def cancel_platform_orders(self, game_id: str, platform_id: str) -> int:
        """Remove all queued orders for a platform.  Returns count removed."""
        key = RKeys.order_queue(game_id)
        all_raw: list[str] = await self._r.zrange(key, 0, -1)
        to_remove = []
        for raw in all_raw:
            try:
                d = json.loads(raw)
                if d.get("platform_id") == platform_id:
                    to_remove.append(raw)
            except (json.JSONDecodeError, KeyError):
                pass
        if to_remove:
            await self._r.zrem(key, *to_remove)
        return len(to_remove)

    async def clear_game(self, game_id: str) -> None:
        await self._r.delete(RKeys.order_queue(game_id))

    # ── Convenience constructors ───────────────────────────────────────────

    @staticmethod
    def make_move_order(
        game_id: str,
        platform_id: str,
        waypoints: list[list[float]],
        speed_knots: float | None = None,
        priority: OrderPriority = OrderPriority.ROUTINE,
        tick: int = 0,
    ) -> PlatformOrder:
        from .models import OrderWaypoint
        wps = [
            OrderWaypoint(lon=wp[0], lat=wp[1], speed_override_knots=speed_knots)
            for wp in waypoints
        ]
        return PlatformOrder(
            id=str(uuid.uuid4()),
            game_id=game_id,
            platform_id=platform_id,
            order_type=OrderType.MOVE_TO,
            priority=priority,
            submission_tick=tick,
            waypoints=wps,
            target_speed_knots=speed_knots,
        )

    @staticmethod
    def make_rtb_order(
        game_id: str,
        platform_id: str,
        rtb_position: list[float],
        priority: OrderPriority = OrderPriority.LOGISTICS,
        tick: int = 0,
    ) -> PlatformOrder:
        from .models import OrderWaypoint
        return PlatformOrder(
            id=str(uuid.uuid4()),
            game_id=game_id,
            platform_id=platform_id,
            order_type=OrderType.RTB,
            priority=priority,
            submission_tick=tick,
            waypoints=[OrderWaypoint(lon=rtb_position[0], lat=rtb_position[1], action="RTB")],
        )

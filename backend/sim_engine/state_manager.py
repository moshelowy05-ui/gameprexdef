"""
StateManager — two-tier storage for live simulation state.

HOT TIER  (Redis HASH, per platform):
  - Read/written every tick
  - Expires after 2 minutes if not refreshed (safety net against zombie state)
  - Key: sim:plat:{platform_id}:hot

WARM TIER (PostgreSQL, PlatformORM):
  - Written every DB_FLUSH_EVERY_N_TICKS ticks, or on significant events
  - Source of truth on process restart / failover
  - Always readable as fallback when Redis misses

PlatformType stats (burn rate, speed, etc.) are cached in Redis for the
duration of the game — they never change, no need to re-query per tick.

Load time complexity: O(N) pipeline reads where N = active platforms.
Write time complexity: O(D) where D = dirty platforms (often << N).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db_models import GameSessionORM, PlatformORM, PlatformTypeORM
from shared.database import async_session_factory
from .models import PlatformHotState, MovementState, RKeys

log = logging.getLogger(__name__)

# Flush dirty platform rows to PostgreSQL every N ticks.
# Between flushes, the authoritative state lives in Redis.
DB_FLUSH_EVERY_N_TICKS = 10

# Redis TTL for hot state (seconds). Much longer than the flush interval —
# this is only a safety net, not the flush trigger.
HOT_STATE_TTL = 300   # 5 minutes
MOVEMENT_TTL  = 3600  # 1 hour (movement plans persist across pauses)

# Nuclear-powered hull types (no fuel burn)
_NUCLEAR_HULL_PREFIXES = ("CVN_", "SSN_", "SSBN_")


def _is_nuclear(type_key: str) -> bool:
    return any(type_key.startswith(p) for p in _NUCLEAR_HULL_PREFIXES)


class StateManager:
    """
    Manages reading and writing PlatformHotState during the tick loop.

    Lifecycle per tick:
      1. load_game_platforms(game_id)  → dict[platform_id, PlatformHotState]
      2. ... subsystems mutate PlatformHotState objects, set .is_dirty = True
      3. flush_dirty(platforms, tick)  → writes Redis + conditionally DB
    """

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    # ── Load ─────────────────────────────────────────────────────────────────

    async def load_game_platforms(
        self, game_id: str
    ) -> dict[str, PlatformHotState]:
        """
        Load all active platforms for a game into hot state.

        Strategy:
          1. Get platform ID set from Redis.
          2. Pipeline-read hot state HASHes for all IDs.
          3. For any misses, fall back to DB and warm the cache.

        Returns dict keyed by platform_id.
        Time complexity: O(N) pipeline reads.
        """
        platform_ids: set[str] = await self._r.smembers(
            RKeys.game_platform_ids(game_id)
        )

        if not platform_ids:
            # Cold start — prime the cache from DB
            platform_ids = await self._prime_from_db(game_id)

        if not platform_ids:
            return {}

        # Batch-read all hot state HASHes in one pipeline
        pipe = self._r.pipeline(transaction=False)
        pid_list = sorted(platform_ids)  # sorted for determinism
        for pid in pid_list:
            pipe.hgetall(RKeys.platform_hot(pid))
        raw_states: list[dict[str, str]] = await pipe.execute()

        platforms: dict[str, PlatformHotState] = {}
        missing_ids: list[str] = []

        for pid, raw in zip(pid_list, raw_states):
            if raw:
                try:
                    platforms[pid] = self._deserialise_hot(pid, game_id, raw)
                    continue
                except (KeyError, ValueError) as exc:
                    log.warning("Corrupt hot state for %s: %s — reloading from DB", pid, exc)
            missing_ids.append(pid)

        if missing_ids:
            db_platforms = await self._load_platforms_from_db(game_id, missing_ids)
            platforms.update(db_platforms)
            await self._warm_cache(list(db_platforms.values()))

        return platforms

    async def load_movement_states(
        self, platform_ids: list[str]
    ) -> dict[str, MovementState | None]:
        """
        Batch-load movement state for a set of platforms.
        Returns None for platforms with no active movement plan.
        """
        if not platform_ids:
            return {}
        pipe = self._r.pipeline(transaction=False)
        for pid in platform_ids:
            pipe.get(RKeys.platform_movement(pid))
        raw_list: list[str | None] = await pipe.execute()

        result: dict[str, MovementState | None] = {}
        for pid, raw in zip(platform_ids, raw_list):
            if raw:
                try:
                    d = json.loads(raw)
                    result[pid] = MovementState(
                        waypoints=d["waypoints"],
                        current_wp_index=d.get("current_wp_index", 0),
                        hold_ticks_remaining=d.get("hold_ticks_remaining", 0),
                        patrol_loop=d.get("patrol_loop", False),
                        rtb_position=d.get("rtb_position"),
                    )
                except (json.JSONDecodeError, KeyError):
                    result[pid] = None
            else:
                result[pid] = None
        return result

    async def save_movement_state(self, platform_id: str, state: MovementState) -> None:
        d = {
            "waypoints": state.waypoints,
            "current_wp_index": state.current_wp_index,
            "hold_ticks_remaining": state.hold_ticks_remaining,
            "patrol_loop": state.patrol_loop,
            "rtb_position": state.rtb_position,
        }
        await self._r.set(
            RKeys.platform_movement(platform_id),
            json.dumps(d),
            ex=MOVEMENT_TTL,
        )

    async def save_movement_states_batch(
        self, states: dict[str, MovementState]
    ) -> None:
        """Batch-save movement states via pipeline."""
        if not states:
            return
        pipe = self._r.pipeline(transaction=False)
        for pid, state in states.items():
            d = {
                "waypoints": state.waypoints,
                "current_wp_index": state.current_wp_index,
                "hold_ticks_remaining": state.hold_ticks_remaining,
                "patrol_loop": state.patrol_loop,
                "rtb_position": state.rtb_position,
            }
            pipe.set(RKeys.platform_movement(pid), json.dumps(d), ex=MOVEMENT_TTL)
        await pipe.execute()

    async def clear_movement_state(self, platform_id: str) -> None:
        await self._r.delete(RKeys.platform_movement(platform_id))

    # ── Flush ─────────────────────────────────────────────────────────────────

    async def flush_dirty(
        self, platforms: dict[str, PlatformHotState], tick: int
    ) -> int:
        """
        Write dirty platforms to Redis hot cache.
        If tick % DB_FLUSH_EVERY_N_TICKS == 0, also persist to PostgreSQL.

        Returns count of dirty platforms written.
        """
        dirty = [p for p in platforms.values() if p.is_dirty]
        if not dirty:
            return 0

        await self._warm_cache(dirty)

        if tick % DB_FLUSH_EVERY_N_TICKS == 0:
            await self._flush_to_db(dirty, tick)

        # Reset dirty flags
        for p in dirty:
            p.is_dirty = False

        return len(dirty)

    async def update_game_tick(self, game_id: str, tick: int) -> None:
        """Persist the current tick counter to DB + Redis."""
        await self._r.set(RKeys.game_tick(game_id), tick, ex=HOT_STATE_TTL)
        async with async_session_factory() as session:
            result = await session.execute(
                select(GameSessionORM).where(GameSessionORM.id == game_id)  # type: ignore
            )
            gs = result.scalar_one_or_none()
            if gs:
                gs.current_tick = tick
                await session.commit()

    # ── Cache warming ─────────────────────────────────────────────────────────

    async def _warm_cache(self, platforms: list[PlatformHotState]) -> None:
        """Write PlatformHotState list to Redis HASHes via pipeline."""
        if not platforms:
            return
        pipe = self._r.pipeline(transaction=False)
        for p in platforms:
            key = RKeys.platform_hot(p.id)
            pipe.hset(key, mapping=self._serialise_hot(p))
            pipe.expire(key, HOT_STATE_TTL)
        await pipe.execute()

    # ── DB operations ─────────────────────────────────────────────────────────

    async def _prime_from_db(self, game_id: str) -> set[str]:
        """
        Cold-start: load all platforms from DB, write to Redis,
        populate the game's platform ID set.
        """
        platforms = await self._load_platforms_from_db(game_id, None)
        if platforms:
            await self._warm_cache(list(platforms.values()))
            pipe = self._r.pipeline(transaction=False)
            pipe.delete(RKeys.game_platform_ids(game_id))
            pipe.sadd(RKeys.game_platform_ids(game_id), *platforms.keys())
            pipe.expire(RKeys.game_platform_ids(game_id), HOT_STATE_TTL)
            await pipe.execute()
        return set(platforms.keys())

    async def _load_platforms_from_db(
        self, game_id: str, platform_ids: list[str] | None
    ) -> dict[str, PlatformHotState]:
        """Load platforms from DB, joining PlatformType for burn rates."""
        async with async_session_factory() as session:
            stmt = (
                select(PlatformORM, PlatformTypeORM)
                .join(PlatformTypeORM, PlatformORM.type_key == PlatformTypeORM.type_key)
                .where(
                    PlatformORM.session_id == game_id,  # type: ignore
                    PlatformORM.status.notin_(["DESTROYED", "RETIRED"]),
                )
            )
            if platform_ids:
                import uuid
                stmt = stmt.where(
                    PlatformORM.id.in_([uuid.UUID(p) for p in platform_ids])
                )
            result = await session.execute(stmt)
            rows = result.all()

        platforms: dict[str, PlatformHotState] = {}
        for platform_orm, ptype_orm in rows:
            pid = str(platform_orm.id)
            platforms[pid] = PlatformHotState(
                id=pid,
                game_id=game_id,
                type_key=platform_orm.type_key,
                faction=platform_orm.faction,
                status=platform_orm.status,
                pos_lon=platform_orm.position_lon or 0.0,
                pos_lat=platform_orm.position_lat or 0.0,
                heading=platform_orm.heading or 0.0,
                speed_knots=platform_orm.speed or 0.0,
                fuel_state=platform_orm.fuel_state,
                health=platform_orm.health,
                fuel_burn_rate_per_tick=ptype_orm.fuel_burn_rate_per_tick,
                fuel_capacity_lbs=ptype_orm.fuel_capacity_lbs,
                cruise_speed_knots=ptype_orm.cruise_speed_knots,
                max_range_nm=ptype_orm.max_range_nm,
                is_nuclear=_is_nuclear(platform_orm.type_key),
            )
        return platforms

    async def _flush_to_db(self, dirty: list[PlatformHotState], tick: int) -> None:
        """Batch-update dirty platforms in PostgreSQL."""
        if not dirty:
            return
        import uuid
        async with async_session_factory() as session:
            id_to_state = {uuid.UUID(p.id): p for p in dirty}
            result = await session.execute(
                select(PlatformORM).where(
                    PlatformORM.id.in_(list(id_to_state.keys()))
                )
            )
            rows = result.scalars().all()
            for row in rows:
                state = id_to_state[row.id]
                row.position_lon = state.pos_lon
                row.position_lat = state.pos_lat
                row.heading       = state.heading
                row.speed         = state.speed_knots
                row.fuel_state    = state.fuel_state
                row.health        = state.health
                row.status        = state.status
            await session.commit()
        log.debug("DB flush: %d platforms at tick %d", len(dirty), tick)

    # ── Serialisation ─────────────────────────────────────────────────────────

    @staticmethod
    def _serialise_hot(p: PlatformHotState) -> dict[str, str]:
        return {
            "game_id":                p.game_id,
            "type_key":               p.type_key,
            "faction":                p.faction,
            "status":                 p.status,
            "pos_lon":                str(p.pos_lon),
            "pos_lat":                str(p.pos_lat),
            "heading":                str(p.heading),
            "speed_knots":            str(p.speed_knots),
            "fuel_state":             str(p.fuel_state),
            "health":                 str(p.health),
            "fuel_burn_rate_per_tick":str(p.fuel_burn_rate_per_tick),
            "fuel_capacity_lbs":      str(p.fuel_capacity_lbs),
            "cruise_speed_knots":     str(p.cruise_speed_knots),
            "max_range_nm":           str(p.max_range_nm),
            "is_nuclear":             "1" if p.is_nuclear else "0",
        }

    @staticmethod
    def _deserialise_hot(
        pid: str, game_id: str, raw: dict[str, str]
    ) -> PlatformHotState:
        return PlatformHotState(
            id=pid,
            game_id=raw.get("game_id", game_id),
            type_key=raw["type_key"],
            faction=raw["faction"],
            status=raw["status"],
            pos_lon=float(raw["pos_lon"]),
            pos_lat=float(raw["pos_lat"]),
            heading=float(raw["heading"]),
            speed_knots=float(raw["speed_knots"]),
            fuel_state=float(raw["fuel_state"]),
            health=float(raw["health"]),
            fuel_burn_rate_per_tick=float(raw["fuel_burn_rate_per_tick"]),
            fuel_capacity_lbs=float(raw["fuel_capacity_lbs"]),
            cruise_speed_knots=float(raw["cruise_speed_knots"]),
            max_range_nm=float(raw["max_range_nm"]),
            is_nuclear=raw.get("is_nuclear", "0") == "1",
        )

    # ── Game lifecycle ─────────────────────────────────────────────────────────

    async def register_game(self, game_id: str) -> None:
        """Mark a game as active in the sim registry."""
        await self._r.sadd(RKeys.active_games(), game_id)

    async def unregister_game(self, game_id: str) -> None:
        """Remove game from active registry and expire its keys."""
        await self._r.srem(RKeys.active_games(), game_id)
        # Let TTLs expire naturally — don't mass-delete to avoid blocking

    async def active_game_ids(self) -> set[str]:
        return await self._r.smembers(RKeys.active_games())

    async def add_platform_to_game(
        self, game_id: str, platform: PlatformHotState
    ) -> None:
        """Register a new platform mid-game (production delivery, etc.)."""
        await self._r.sadd(RKeys.game_platform_ids(game_id), platform.id)
        await self._warm_cache([platform])

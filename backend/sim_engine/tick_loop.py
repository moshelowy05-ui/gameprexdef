"""
AsyncTickRunner — manages per-game asyncio tick loops.

Architecture:
  - One asyncio.Task per active game (created on resume, cancelled on pause).
  - A single background "watchdog" task recovers games that were running
    when the server restarted (checks Redis `sim:active_games` on startup).
  - Speed control: tick interval = REAL_SECONDS_PER_TICK / speed_multiplier.
  - The runner does NOT block FastAPI request handling — all work is async.

Real-time tick rates at different speed multipliers (REAL_SECONDS_PER_TICK=5):
  1x  → 1 game hour per 5 real seconds
  5x  → 1 game hour per 1 real second
  10x → 1 game hour per 0.5 real seconds
  50x → 1 game hour per 0.1 real seconds (fast forward / test mode)

WebSocket broadcast:
  After each tick, the runner emits two events to the game's Socket.IO room:
    - "tick"              { tick, paused: false }
    - "platform_updates"  [ PlatformDelta, ... ]  (delta-compressed, not full state)

  At high speed (≥ 10x), platform_updates are throttled to at most one
  broadcast per BROADCAST_THROTTLE_SECONDS real seconds to avoid flooding
  the client, but the "tick" event is always sent.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import socketio as socketio_module

from shared.redis_client import get_redis
from .engine import TickEngine
from .models import PlatformDelta, TickResult
from .state_manager import StateManager

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

REAL_SECONDS_PER_GAME_HOUR: float = 5.0   # at 1x speed
BROADCAST_THROTTLE_SECONDS: float = 0.5   # min real-seconds between position broadcasts
MAX_CONSECUTIVE_ERRORS: int = 5            # pause game after this many tick errors
MAX_TICK_BUDGET_MS: float = 2000.0        # alert if tick takes longer than this


# ── Per-game state ────────────────────────────────────────────────────────────

class _GameRunState:
    __slots__ = (
        "game_id", "task", "engine", "speed", "current_tick",
        "error_count", "last_broadcast_time",
    )

    def __init__(
        self,
        game_id: str,
        engine: TickEngine,
        speed: float,
        current_tick: int,
    ) -> None:
        self.game_id = game_id
        self.task: asyncio.Task | None = None
        self.engine = engine
        self.speed = speed
        self.current_tick = current_tick
        self.error_count = 0
        self.last_broadcast_time: float = 0.0


# ── Runner ────────────────────────────────────────────────────────────────────

class AsyncTickRunner:
    """
    Manages the asyncio tick loop for all active game sessions.

    Instantiated once per process, attached to `app.state.tick_runner`
    via FastAPI lifespan.  Routers call pause_game / resume_game / set_speed.
    """

    def __init__(self, sio: socketio_module.AsyncServer) -> None:
        self._sio = sio
        self._games: dict[str, _GameRunState] = {}
        self._redis = get_redis()
        self._state_manager = StateManager(self._redis)
        self._watchdog_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Called from FastAPI lifespan on startup."""
        self._watchdog_task = asyncio.create_task(
            self._watchdog(), name="tick-runner-watchdog"
        )
        log.info("AsyncTickRunner started")

    async def stop_all(self) -> None:
        """Called from FastAPI lifespan on shutdown.  Cancels all tasks."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
        for run_state in list(self._games.values()):
            await self._cancel_task(run_state)
            await run_state.engine.teardown()
        self._games.clear()
        log.info("AsyncTickRunner stopped")

    # ── Public control API (called by game router) ────────────────────────────

    async def resume_game(self, game_id: str, speed: float = 1.0) -> None:
        """Start or resume the tick loop for a game."""
        if game_id in self._games:
            run_state = self._games[game_id]
            run_state.speed = speed
            if run_state.task is None or run_state.task.done():
                run_state.task = asyncio.create_task(
                    self._tick_loop(run_state), name=f"tick-{game_id[:8]}"
                )
        else:
            # New game — create engine and start loop
            engine = TickEngine(game_id=game_id, redis=self._redis)
            await self._state_manager.register_game(game_id)

            # Get current tick from DB
            current_tick = await self._get_current_tick(game_id)

            run_state = _GameRunState(
                game_id=game_id,
                engine=engine,
                speed=speed,
                current_tick=current_tick,
            )
            self._games[game_id] = run_state
            run_state.task = asyncio.create_task(
                self._tick_loop(run_state), name=f"tick-{game_id[:8]}"
            )
        log.info("Game %s resumed at %.1fx speed", game_id[:8], speed)

    async def pause_game(self, game_id: str) -> None:
        """Pause the tick loop for a game (keeps state in Redis)."""
        run_state = self._games.get(game_id)
        if run_state:
            await self._cancel_task(run_state)
            log.info("Game %s paused at tick %d", game_id[:8], run_state.current_tick)

    async def set_speed(self, game_id: str, speed: float) -> None:
        """Adjust tick speed without pausing.  Takes effect on the next tick."""
        run_state = self._games.get(game_id)
        if run_state:
            run_state.speed = speed
            log.info("Game %s speed set to %.1fx", game_id[:8], speed)

    async def stop_game(self, game_id: str) -> None:
        """Fully stop and remove a game (e.g., on delete)."""
        run_state = self._games.pop(game_id, None)
        if run_state:
            await self._cancel_task(run_state)
            await run_state.engine.teardown()

    def get_running_game_ids(self) -> list[str]:
        return [
            gid for gid, rs in self._games.items()
            if rs.task is not None and not rs.task.done()
        ]

    # ── Core tick loop ────────────────────────────────────────────────────────

    async def _tick_loop(self, run_state: _GameRunState) -> None:
        """
        Asyncio task body: runs ticks at the configured speed until cancelled.

        Each iteration:
          1. Run TickEngine.run_tick()
          2. Broadcast results via Socket.IO
          3. Sleep for the remaining tick interval (wall-time adjusted)
        """
        import time

        game_id = run_state.game_id
        log.debug("Tick loop started for game %s", game_id[:8])

        try:
            while True:
                tick_start = time.monotonic()
                tick = run_state.current_tick

                # ── Execute tick ──────────────────────────────────────────────
                try:
                    result = await run_state.engine.run_tick(tick)
                    run_state.error_count = 0
                except Exception as exc:
                    run_state.error_count += 1
                    log.error(
                        "Tick %d error for game %s (%d/%d): %s",
                        tick, game_id[:8], run_state.error_count,
                        MAX_CONSECUTIVE_ERRORS, exc,
                    )
                    if run_state.error_count >= MAX_CONSECUTIVE_ERRORS:
                        log.critical(
                            "Game %s auto-paused after %d consecutive errors",
                            game_id[:8], MAX_CONSECUTIVE_ERRORS,
                        )
                        await self._broadcast_alert(
                            game_id,
                            level="critical",
                            title="SIM ERROR — AUTO PAUSED",
                            body=f"Simulation halted after {MAX_CONSECUTIVE_ERRORS} "
                                 f"consecutive tick failures. Check server logs.",
                        )
                        return  # exit the loop — game effectively paused
                    # Single error: skip broadcast, advance tick anyway
                    result = None

                # ── Broadcast ─────────────────────────────────────────────────
                run_state.current_tick = tick + 1
                if result is not None:
                    await self._broadcast_result(run_state, result)

                # ── Sleep for remaining tick budget ───────────────────────────
                tick_duration = REAL_SECONDS_PER_GAME_HOUR / run_state.speed
                elapsed = time.monotonic() - tick_start
                sleep_for = max(0.0, tick_duration - elapsed)
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                # If elapsed > tick_duration, we're behind — run next tick immediately

        except asyncio.CancelledError:
            log.debug("Tick loop cancelled for game %s", game_id[:8])
            raise

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def _broadcast_result(
        self, run_state: _GameRunState, result: TickResult
    ) -> None:
        """Emit tick event and (throttled) platform deltas to Socket.IO room."""
        import time

        room = f"game:{run_state.game_id}"

        # Always emit tick counter
        await self._sio.emit(
            "tick",
            {"tick": result.tick, "paused": False},
            room=room,
        )

        # Throttle position broadcasts at high speed
        now = time.monotonic()
        should_broadcast_positions = (
            now - run_state.last_broadcast_time >= BROADCAST_THROTTLE_SECONDS
        )

        if result.deltas and should_broadcast_positions:
            run_state.last_broadcast_time = now
            await self._sio.emit(
                "platform_updates",
                [d.model_dump(exclude_none=True) for d in result.deltas],
                room=room,
            )

        # Emit significant events as alerts
        for ev in result.events:
            if ev.type.value in ("FUEL_LOW", "FUEL_BINGO", "FUEL_EXHAUSTED",
                                  "MISSION_COMPLETE", "RTB_TRIGGERED"):
                level = "critical" if "BINGO" in ev.type.value or "EXHAUSTED" in ev.type.value \
                        else "warning"
                await self._sio.emit(
                    "alert",
                    {"level": level, "title": ev.type.value, "body": ev.narrative},
                    room=room,
                )

        # Broadcast combat engagements
        if result.combat_engagements:
            await self._sio.emit(
                "combat_events",
                result.combat_engagements,
                room=room,
            )

        # Broadcast intel track updates
        if result.intel_updates:
            await self._sio.emit(
                "intel_updates",
                result.intel_updates,
                room=room,
            )

        # Broadcast game over
        if result.game_over:
            await self._sio.emit(
                "game_over",
                result.game_over,
                room=room,
            )
            # Auto-pause the game
            await self.pause_game(run_state.game_id)

        # Emit warnings if any
        for w in result.warnings:
            await self._broadcast_alert(run_state.game_id, "warning", "TICK WARNING", w)

    async def _broadcast_alert(
        self, game_id: str, level: str, title: str, body: str
    ) -> None:
        await self._sio.emit(
            "alert",
            {"level": level, "title": title, "body": body},
            room=f"game:{game_id}",
        )

    # ── Watchdog ──────────────────────────────────────────────────────────────

    async def _watchdog(self) -> None:
        """
        On startup, resume any games that were running before server restart.
        Runs once at startup then exits.
        """
        try:
            active_ids = await self._state_manager.active_game_ids()
            if active_ids:
                log.info(
                    "Watchdog found %d active games in Redis — resuming", len(active_ids)
                )
                for game_id in active_ids:
                    if game_id not in self._games:
                        tick = await self._get_current_tick(game_id)
                        log.info(
                            "Watchdog resuming game %s at tick %d", game_id[:8], tick
                        )
                        await self.resume_game(game_id, speed=1.0)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("Watchdog error: %s", exc)

    # ── Utilities ─────────────────────────────────────────────────────────────

    async def _cancel_task(self, run_state: _GameRunState) -> None:
        if run_state.task and not run_state.task.done():
            run_state.task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(run_state.task), timeout=2.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        run_state.task = None

    async def _get_current_tick(self, game_id: str) -> int:
        """Read current tick from Redis (fast) or DB (fallback)."""
        from shared.redis_client import get_redis
        from sim_engine.models import RKeys
        redis = get_redis()
        val = await redis.get(RKeys.game_tick(game_id))
        if val is not None:
            return int(val)
        # DB fallback
        from shared.database import async_session_factory
        from shared.db_models import GameSessionORM
        from sqlalchemy import select
        import uuid
        async with async_session_factory() as session:
            result = await session.execute(
                select(GameSessionORM.current_tick).where(
                    GameSessionORM.id == uuid.UUID(game_id)
                )
            )
            row = result.scalar_one_or_none()
            return row or 0

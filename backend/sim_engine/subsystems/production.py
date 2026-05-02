"""
ProductionSubsystem — advance production queues each tick.

Each facility has a production_queue (JSON list of ProductionOrder-like dicts).
Each tick: increment ticks_elapsed on all in-progress orders.
When ticks_elapsed >= ticks_per_unit: deliver one unit (create PlatformORM row).
"""
from __future__ import annotations

import logging
import random
import uuid

log = logging.getLogger(__name__)


class ProductionSubsystem:
    """
    Advances facility production queues each tick and creates PlatformORM rows
    when units are delivered.
    """

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

    async def advance_tick(
        self, db_session, game_id: str, tick: int
    ) -> list[dict]:
        """
        Advance all production queues by one tick.

        Returns a list of delivery dicts for platforms delivered this tick:
            {"facility_id": str, "type_key": str, "platform_id": str, "tick": int}
        """
        from sqlalchemy import select
        from shared.db_models import FacilityORM, PlatformORM

        deliveries: list[dict] = []

        try:
            result = await db_session.execute(
                select(FacilityORM).where(
                    FacilityORM.session_id == uuid.UUID(game_id),
                    FacilityORM.power_state != "OFFLINE",
                )
            )
            facilities = result.scalars().all()

            for facility in facilities:
                queue: list[dict] = list(facility.production_queue or [])
                if not queue:
                    continue

                updated_queue: list[dict] = []
                queue_dirty = False

                for order in queue:
                    ticks_elapsed = order.get("ticks_elapsed", 0) + 1
                    ticks_per_unit = order.get("ticks_per_unit", 1)
                    quantity_remaining = order.get("quantity_remaining", 1)
                    type_key = order.get("type_key", "UNKNOWN")

                    order = dict(order)  # shallow copy to avoid mutating original
                    order["ticks_elapsed"] = ticks_elapsed
                    queue_dirty = True

                    if ticks_elapsed >= ticks_per_unit:
                        # Deliver one unit
                        new_platform_id = str(uuid.uuid4())
                        offset_lon = facility.position_lon + random.uniform(-0.02, 0.02)
                        offset_lat = facility.position_lat + random.uniform(-0.02, 0.02)

                        new_platform = PlatformORM(
                            id=uuid.UUID(new_platform_id),
                            session_id=facility.session_id,
                            designation=f"{type_key}-{new_platform_id[:8].upper()}",
                            platform_class=type_key.split("_")[0] if "_" in type_key else type_key,
                            type_key=type_key,
                            faction="US",
                            status="ACTIVE",
                            position_lon=offset_lon,
                            position_lat=offset_lat,
                            heading=0.0,
                            speed=0.0,
                            altitude=None,
                            fuel_state=1.0,
                            health=1.0,
                            maintenance_due_tick=tick + 720,
                            created_tick=tick,
                            ammo_state={},
                            sensor_suite={},
                        )
                        db_session.add(new_platform)

                        deliveries.append({
                            "facility_id": str(facility.id),
                            "type_key": type_key,
                            "platform_id": new_platform_id,
                            "tick": tick,
                        })

                        log.info(
                            "Production delivery: %s (platform %s) from facility %s at tick %d",
                            type_key, new_platform_id[:8], str(facility.id)[:8], tick,
                        )

                        quantity_remaining -= 1
                        order["quantity_remaining"] = quantity_remaining
                        order["ticks_elapsed"] = 0  # reset for next unit

                        if quantity_remaining > 0:
                            updated_queue.append(order)
                        # else: order complete, drop from queue
                    else:
                        updated_queue.append(order)

                if queue_dirty:
                    facility.production_queue = updated_queue

            await db_session.commit()

        except Exception as exc:
            log.error(
                "ProductionSubsystem.advance_tick error (game=%s, tick=%d): %s",
                game_id, tick, exc,
            )

        log.debug(
            "Production tick %d (game=%s) — %d deliveries",
            tick, game_id, len(deliveries),
        )
        return deliveries

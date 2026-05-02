"""
ProductionSubsystem — advance production queues each tick.

Each facility has a production_queue (JSON list of ProductionOrder-like dicts).
Each tick: increment ticks_elapsed on all in-progress orders.
When ticks_elapsed >= ticks_per_unit: deliver one unit (create PlatformORM row).

Phase 2 implementation: in-memory queue advancement only (DB writes happen in flush).
The ProductionSubsystem reads facility data from DB and writes back.

Phase 3 will implement actual PlatformORM creation on delivery.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class ProductionSubsystem:
    """
    Stub implementation for Phase 2.

    Logs that production is running each tick and returns an empty delivery list.
    Full queue advancement and platform creation are deferred to Phase 3.
    """

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

    def advance_tick(self, tick: int) -> list[str]:
        """
        Advance all production queues by one tick.

        Returns a list of type_keys for platforms that have been delivered
        this tick (empty in Phase 2).
        """
        log.debug("Production tick %d (game=%s)", tick, self._game_id)
        return []

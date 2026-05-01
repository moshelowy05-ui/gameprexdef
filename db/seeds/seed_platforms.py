"""
Seed the platform_types table from platform_types.json.
Run from repo root: python db/seeds/seed_platforms.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import asyncpg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://gameprex:gameprex_dev@localhost:5432/gameprexdef"
)
# asyncpg uses plain postgresql:// — strip asyncpg if present
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

SEED_FILE = Path(__file__).parent / "platform_types.json"


async def seed() -> None:
    conn = await asyncpg.connect(DATABASE_URL)

    with open(SEED_FILE) as f:
        platform_types = json.load(f)

    inserted = 0
    updated = 0

    for pt in platform_types:
        import json as _json
        existing = await conn.fetchrow(
            "SELECT type_key FROM platform_types WHERE type_key = $1", pt["type_key"]
        )
        if existing:
            await conn.execute(
                """
                UPDATE platform_types SET
                    display_name = $2, category = $3, faction = $4, service = $5,
                    max_speed_knots = $6, cruise_speed_knots = $7, max_range_nm = $8,
                    fuel_capacity_lbs = $9, fuel_burn_rate_per_tick = $10,
                    crew_requirement = $11, build_time_ticks = $12,
                    maintenance_interval_ticks = $13, description = $14,
                    hardpoints = $15, sensor_suite = $16, signature = $17,
                    build_cost = $18, upgrade_paths = $19
                WHERE type_key = $1
                """,
                pt["type_key"], pt["display_name"], pt["category"], pt["faction"],
                pt.get("service", ""),
                pt["max_speed_knots"], pt["cruise_speed_knots"], pt["max_range_nm"],
                pt["fuel_capacity_lbs"], pt["fuel_burn_rate_per_tick"],
                pt["crew_requirement"], pt["build_time_ticks"],
                pt["maintenance_interval_ticks"], pt.get("description", ""),
                _json.dumps(pt.get("hardpoints", [])),
                _json.dumps(pt.get("sensor_suite", {})),
                _json.dumps(pt.get("signature", {})),
                _json.dumps(pt.get("build_cost", {})),
                _json.dumps(pt.get("upgrade_paths", [])),
            )
            updated += 1
        else:
            await conn.execute(
                """
                INSERT INTO platform_types (
                    type_key, display_name, category, faction, service,
                    max_speed_knots, cruise_speed_knots, max_range_nm,
                    fuel_capacity_lbs, fuel_burn_rate_per_tick,
                    crew_requirement, build_time_ticks, maintenance_interval_ticks,
                    description, hardpoints, sensor_suite, signature,
                    build_cost, upgrade_paths
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                """,
                pt["type_key"], pt["display_name"], pt["category"], pt["faction"],
                pt.get("service", ""),
                pt["max_speed_knots"], pt["cruise_speed_knots"], pt["max_range_nm"],
                pt["fuel_capacity_lbs"], pt["fuel_burn_rate_per_tick"],
                pt["crew_requirement"], pt["build_time_ticks"],
                pt["maintenance_interval_ticks"], pt.get("description", ""),
                _json.dumps(pt.get("hardpoints", [])),
                _json.dumps(pt.get("sensor_suite", {})),
                _json.dumps(pt.get("signature", {})),
                _json.dumps(pt.get("build_cost", {})),
                _json.dumps(pt.get("upgrade_paths", [])),
            )
            inserted += 1

    await conn.close()
    print(f"Seeded {inserted} new platform types, updated {updated} existing.")


if __name__ == "__main__":
    asyncio.run(seed())

"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_types",
        sa.Column("type_key", sa.String(100), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("faction", sa.String(50), nullable=False),
        sa.Column("max_speed_knots", sa.Float(), nullable=False),
        sa.Column("cruise_speed_knots", sa.Float(), nullable=False),
        sa.Column("max_range_nm", sa.Float(), nullable=False),
        sa.Column("fuel_capacity_lbs", sa.Float(), nullable=False),
        sa.Column("fuel_burn_rate_per_tick", sa.Float(), nullable=False),
        sa.Column("crew_requirement", sa.Integer(), nullable=False),
        sa.Column("build_time_ticks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maintenance_interval_ticks", sa.Integer(), nullable=False, server_default="720"),
        sa.Column("service", sa.String(20), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("hardpoints", JSONB(), nullable=False, server_default="[]"),
        sa.Column("sensor_suite", JSONB(), nullable=False, server_default="{}"),
        sa.Column("signature", JSONB(), nullable=False, server_default="{}"),
        sa.Column("build_cost", JSONB(), nullable=False, server_default="{}"),
        sa.Column("upgrade_paths", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "game_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", sa.String(100), nullable=False),
        sa.Column("current_tick", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("tick_speed_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("state_snapshot", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "platforms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("designation", sa.String(200), nullable=False),
        sa.Column("platform_class", sa.String(50), nullable=False),
        sa.Column(
            "type_key",
            sa.String(100),
            sa.ForeignKey("platform_types.type_key"),
            nullable=False,
        ),
        sa.Column("faction", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("position_lon", sa.Float(), nullable=True),
        sa.Column("position_lat", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("fuel_state", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("health", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("maintenance_due_tick", sa.Integer(), nullable=False, server_default="720"),
        sa.Column("assigned_mission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_tf_id", UUID(as_uuid=True), nullable=True),
        sa.Column("parent_platform_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_tick", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("destroyed_tick", sa.Integer(), nullable=True),
        sa.Column("ammo_state", JSONB(), nullable=False, server_default="{}"),
        sa.Column("sensor_suite", JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_platforms_session_id", "platforms", ["session_id"])
    op.create_index("ix_platforms_faction", "platforms", ["faction"])
    op.create_index("ix_platforms_status", "platforms", ["status"])

    op.create_table(
        "task_forces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("commander_unit_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_unit_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("mission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("formation", JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), nullable=False, server_default="ASSEMBLING"),
        sa.Column("logistics_node_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_task_forces_session_id", "task_forces", ["session_id"])

    op.create_table(
        "missions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("mission_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PLANNED"),
        sa.Column("assigned_tf_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target", JSONB(), nullable=False, server_default="{}"),
        sa.Column("roe", JSONB(), nullable=False, server_default="{}"),
        sa.Column("start_tick", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_tick", sa.Integer(), nullable=True),
        sa.Column("waypoints", JSONB(), nullable=False, server_default="[]"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("commander_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("events", JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_missions_session_id", "missions", ["session_id"])
    op.create_index("ix_missions_status", "missions", ["status"])

    op.create_table(
        "facilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("facility_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("faction", sa.String(50), nullable=False),
        sa.Column("position_lon", sa.Float(), nullable=False),
        sa.Column("position_lat", sa.Float(), nullable=False),
        sa.Column("production_slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("health", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("workforce", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("power_state", sa.String(50), nullable=False, server_default="OPERATIONAL"),
        sa.Column("production_queue", JSONB(), nullable=False, server_default="[]"),
        sa.Column("storage", JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_facilities_session_id", "facilities", ["session_id"])

    op.create_table(
        "resource_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("faction", sa.String(50), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_billions", sa.Float(), nullable=False),
        sa.Column("budget_burn_rate_per_tick", sa.Float(), nullable=False),
        sa.Column("fuel_reserves_barrels", sa.Float(), nullable=False),
        sa.Column("supply_chain_disruption", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("resources_json", JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "intel_tracks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("faction_observer", sa.String(50), nullable=False),
        sa.Column("target_platform_id", UUID(as_uuid=True), nullable=True),
        sa.Column("track_type", sa.String(50), nullable=False, server_default="POSSIBLE"),
        sa.Column("last_position_lon", sa.Float(), nullable=False),
        sa.Column("last_position_lat", sa.Float(), nullable=False),
        sa.Column("last_updated_tick", sa.Integer(), nullable=False),
        sa.Column("estimated_heading", sa.Float(), nullable=True),
        sa.Column("estimated_speed", sa.Float(), nullable=True),
        sa.Column("platform_type_estimate", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(50), nullable=False),
    )
    op.create_index("ix_intel_tracks_session_id", "intel_tracks", ["session_id"])


def downgrade() -> None:
    op.drop_table("intel_tracks")
    op.drop_table("resource_states")
    op.drop_table("facilities")
    op.drop_table("missions")
    op.drop_table("task_forces")
    op.drop_table("platforms")
    op.drop_table("game_sessions")
    op.drop_table("platform_types")

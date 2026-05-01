"""
SQLAlchemy ORM models — maps to PostgreSQL tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .database import Base


class PlatformTypeORM(Base):
    __tablename__ = "platform_types"

    type_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    faction: Mapped[str] = mapped_column(String(50), nullable=False)
    max_speed_knots: Mapped[float] = mapped_column(Float, nullable=False)
    cruise_speed_knots: Mapped[float] = mapped_column(Float, nullable=False)
    max_range_nm: Mapped[float] = mapped_column(Float, nullable=False)
    fuel_capacity_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    fuel_burn_rate_per_tick: Mapped[float] = mapped_column(Float, nullable=False)
    crew_requirement: Mapped[int] = mapped_column(Integer, nullable=False)
    build_time_ticks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maintenance_interval_ticks: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    service: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON blobs for complex nested structures
    hardpoints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    sensor_suite: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    signature: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    build_cost: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    upgrade_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GameSessionORM(Base):
    __tablename__ = "game_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[str] = mapped_column(String(100), nullable=False)
    current_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tick_speed_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    platforms: Mapped[list[PlatformORM]] = relationship("PlatformORM", back_populates="session")
    missions: Mapped[list[MissionORM]] = relationship("MissionORM", back_populates="session")
    task_forces: Mapped[list[TaskForceORM]] = relationship("TaskForceORM", back_populates="session")
    facilities: Mapped[list[FacilityORM]] = relationship("FacilityORM", back_populates="session")


class PlatformORM(Base):
    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    designation: Mapped[str] = mapped_column(String(200), nullable=False)
    platform_class: Mapped[str] = mapped_column(String(50), nullable=False)
    type_key: Mapped[str] = mapped_column(
        String(100), ForeignKey("platform_types.type_key"), nullable=False
    )
    faction: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    position_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuel_state: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    health: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    maintenance_due_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    assigned_mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_tf_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    parent_platform_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    destroyed_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ammo_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sensor_suite: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    session: Mapped[GameSessionORM] = relationship("GameSessionORM", back_populates="platforms")


class TaskForceORM(Base):
    __tablename__ = "task_forces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    commander_unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assigned_unit_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    formation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ASSEMBLING")
    logistics_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    session: Mapped[GameSessionORM] = relationship("GameSessionORM", back_populates="task_forces")


class MissionORM(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mission_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PLANNED")
    assigned_tf_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    roe: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    start_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waypoints: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    commander_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    session: Mapped[GameSessionORM] = relationship("GameSessionORM", back_populates="missions")


class FacilityORM(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    facility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    faction: Mapped[str] = mapped_column(String(50), nullable=False)
    position_lon: Mapped[float] = mapped_column(Float, nullable=False)
    position_lat: Mapped[float] = mapped_column(Float, nullable=False)
    production_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    health: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    workforce: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    power_state: Mapped[str] = mapped_column(String(50), nullable=False, default="OPERATIONAL")
    production_queue: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    storage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    session: Mapped[GameSessionORM] = relationship("GameSessionORM", back_populates="facilities")


class ResourceStateORM(Base):
    __tablename__ = "resource_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    faction: Mapped[str] = mapped_column(String(50), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget_billions: Mapped[float] = mapped_column(Float, nullable=False)
    budget_burn_rate_per_tick: Mapped[float] = mapped_column(Float, nullable=False)
    fuel_reserves_barrels: Mapped[float] = mapped_column(Float, nullable=False)
    supply_chain_disruption: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    resources_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class IntelTrackORM(Base):
    __tablename__ = "intel_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False
    )
    faction_observer: Mapped[str] = mapped_column(String(50), nullable=False)
    target_platform_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    track_type: Mapped[str] = mapped_column(String(50), nullable=False, default="POSSIBLE")
    last_position_lon: Mapped[float] = mapped_column(Float, nullable=False)
    last_position_lat: Mapped[float] = mapped_column(Float, nullable=False)
    last_updated_tick: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    platform_type_estimate: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

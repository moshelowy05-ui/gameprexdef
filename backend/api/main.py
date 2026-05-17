from contextlib import asynccontextmanager
from typing import AsyncGenerator

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from sim_engine.tick_loop import AsyncTickRunner
    runner = AsyncTickRunner(sio=app.state.sio)  # type: ignore[attr-defined]
    app.state.tick_runner = runner
    await runner.start()
    yield
    await runner.stop_all()


# Socket.IO: allow same origins as FastAPI CORS, plus wildcard in production
# when served from same origin via nginx (no cross-origin needed).
_sio_origins = settings.allowed_origins or "*"

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_sio_origins,
    logger=False,
    engineio_logger=False,
)

app = FastAPI(
    title="GamePrexDef API",
    description="Military Strategy Simulation — National Command Authority Interface",
    version="0.1.0",
    # Disable interactive docs in production (exposes API surface)
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.sio = sio

from .routers import auth, game, platforms, missions, task_forces, facilities, intel, dib  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(platforms.router, prefix="/api/platforms", tags=["platforms"])
app.include_router(missions.router, prefix="/api/missions", tags=["missions"])
app.include_router(task_forces.router, prefix="/api/task-forces", tags=["task_forces"])
app.include_router(facilities.router, prefix="/api/facilities", tags=["facilities"])
app.include_router(intel.router, prefix="/api/intel", tags=["intel"])
app.include_router(dib.router, prefix="/api/dib", tags=["dib"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@sio.event
async def connect(sid: str, environ: dict) -> None:
    await sio.emit("connected", {"sid": sid}, to=sid)


@sio.event
async def disconnect(sid: str) -> None:
    pass


@sio.event
async def join_game(sid: str, data: dict) -> None:
    game_id = data.get("game_id")
    if game_id:
        await sio.enter_room(sid, f"game:{game_id}")
        await sio.emit("joined_game", {"game_id": game_id}, to=sid)


# ── ASGI entrypoint ──────────────────────────────────────────────────────────
# Uvicorn must target `api.main:application`, NOT `api.main:app`.
application = socketio.ASGIApp(sio, app)

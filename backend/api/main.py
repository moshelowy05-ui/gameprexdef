import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import settings
from .routers import auth, game, platforms, missions, task_forces, facilities, intel, dib

app = FastAPI(
    title="GamePrexDef API",
    description="Military Strategy Simulation — National Command Authority Interface",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO for real-time tick/event streaming
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["http://localhost:3000"],
    logger=False,
    engineio_logger=False,
)
socket_app = socketio.ASGIApp(sio, app)

# Store sio on app state for use in routers/services
app.state.sio = sio

# Routers
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

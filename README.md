# GamePrexDef

**Military Strategy Simulation** — a real-time theater-level wargame set in the Indo-Pacific.
Command US forces against an AI-driven PLAN adversary across air, surface, and subsurface domains.

## Features

- **Theater map** with Fog of War — enemies only visible within radar/sensor range
- **C2 system** — click units to move, attack, hold, or RTB
- **Ghost contacts** — intel tracks for out-of-range enemies; attack their last known position
- **Sensor coverage overlay** — visualize your radar rings
- **Live combat** — detection, engagement, and damage resolution every game-tick
- **Mission system** — STRIKE, PATROL, INTERCEPT, RECON, ESCORT, SEAD, ASW
- **Adversary AI** — PLAN carriers-hunt, submarine ambush, H-6 stand-off strikes
- **After-action overlay** — force losses, mission success rate, game outcome

## Quick Start (Development)

### Prerequisites
- Docker + Docker Compose

```bash
git clone <repo>
cd gameprexdef
docker compose up
```

| Service  | URL                      |
|----------|--------------------------|
| Frontend | http://localhost:3000    |
| API docs | http://localhost:8000/docs |
| API      | http://localhost:8000    |

**Default login:** `nca` / `gameprex2024`

Once logged in, select the **Taiwan Strait Crisis** scenario and press **New Game**.

### Controls

| Key     | Action                  |
|---------|-------------------------|
| `Space` | Play / Pause            |
| Click   | Select unit             |
| `M`     | Move mode               |
| `A`     | Attack mode             |
| `H`     | Hold position           |
| `R`     | Return to base (RTB)    |
| `Esc`   | Cancel / deselect       |

---

## Production Deployment

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set all passwords and SECRET_KEY
```

Generate a strong secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Deploy

```bash
docker compose -f docker-compose.prod.yml up -d
```

The production stack runs:
- **nginx** on port 80 (configurable via `BIND_PORT`) — serves the React SPA and proxies `/api` + `/socket.io`
- **api** (uvicorn, single worker) — FastAPI + Socket.IO backend
- **postgres** — game state
- **redis** — pub/sub and session cache

### 3. HTTPS (recommended)

Put a TLS-terminating reverse proxy (Caddy, Traefik, or nginx with Certbot) in front of the `web` container. Example with Caddy:

```
yourdomain.com {
    reverse_proxy localhost:80
}
```

Then set `BIND_PORT=8080` in `.env` to avoid port conflicts.

---

## Architecture

```
browser ──► nginx (port 80)
              ├── /* ──────────► /usr/share/nginx/html (React SPA)
              ├── /api/* ───────► api:8000 (FastAPI)
              └── /socket.io/* ► api:8000 (Socket.IO WS)

api
  ├── FastAPI HTTP routers
  ├── Socket.IO server (tick events, combat, intel, alerts)
  └── AsyncTickRunner
        ├── MovementSubsystem  — great-circle position updates (NumPy)
        ├── CombatSubsystem    — radar detection + engagement resolution
        ├── ISRSubsystem       — intel track generation (drives Fog of War)
        ├── MissionSubsystem   — mission lifecycle
        ├── FuelSubsystem      — fuel burn + RTB triggers
        ├── ProductionSubsystem — DIB build queues
        └── AdversaryAI        — PLAN rule-based tactical planner
```

## Monorepo Layout

```
/frontend        React 18 + TypeScript + Deck.gl
/backend
  /api           FastAPI gateway
  /sim_engine    Tick loop, subsystems, order resolution
  /ai_engine     Adversary AI
  /shared        Pydantic models, config, DB
/db
  /migrations    Alembic migrations
  /seeds         Platform type registry + scenario seeds
/infra           nginx config
/scenarios       JSON scenario definitions
/scripts         Dev setup scripts
```

## Environment Variables

See [`.env.example`](.env.example) for all configuration options.

| Variable           | Description                                 |
|--------------------|---------------------------------------------|
| `POSTGRES_USER`    | Database username                           |
| `POSTGRES_PASSWORD`| Database password                           |
| `POSTGRES_DB`      | Database name                               |
| `REDIS_PASSWORD`   | Redis auth password                         |
| `SECRET_KEY`       | 32-byte hex token for session signing       |
| `CORS_ORIGINS`     | Comma-separated allowed origins (dev only)  |
| `DEFAULT_USERNAME` | Login username (default: `nca`)             |
| `DEFAULT_PASSWORD` | Login password — **change before deploying**|
| `BIND_PORT`        | Host port for nginx (default: `80`)         |

## Development (without Docker)

```bash
# Start infra
./scripts/dev-setup.sh

# Backend
cd backend && pip install -e ".[dev]"
uvicorn api.main:application --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

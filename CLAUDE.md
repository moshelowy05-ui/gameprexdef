# GamePrexDef — Military Strategy Simulation

## Monorepo Structure

```
/frontend        React 18 + TypeScript + Deck.gl dashboard
/backend
  /api           FastAPI gateway (port 8000)
  /sim_engine    Tick loop, order resolution, world clock
  /ai_engine     Adversary strategic/tactical AI
  /shared        Pydantic models and constants (shared truth)
/db
  /migrations    Alembic migrations
  /seeds         PlatformType registry, scenario seed data
/infra           Docker Compose, k8s configs
/scenarios       JSON scenario definitions
```

## Dev Environment

Start everything: `docker compose up`

| Service       | Port  | Description              |
|---------------|-------|--------------------------|
| frontend      | 3000  | React dev server         |
| api           | 8000  | FastAPI (docs at /docs)  |
| postgres      | 5432  | PostgreSQL 16            |
| redis         | 6379  | Redis 7                  |
| timescaledb   | 5433  | TimescaleDB (event log)  |

## Key Conventions

- All entity IDs are UUIDs
- GameTick is an integer (1 tick = 1 game-hour)
- Positions are GeoJSON [lon, lat] arrays
- All monetary values in billions USD
- Fuel states are 0.0–1.0 floats
- Probability rolls are always 0.0–1.0 floats

## Backend

- Python 3.12
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async)
- Alembic for migrations
- `cd backend && pip install -e ".[dev]"` to install

## Frontend

- React 18 + TypeScript 5
- Vite build tool
- `cd frontend && npm install && npm run dev`

## Database

Run migrations: `cd db && alembic upgrade head`
Seed data: `cd db && python seeds/seed_platforms.py`

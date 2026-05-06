#!/usr/bin/env bash
# GamePrexDef — local development setup (no Docker)
# Run once to init the DB and seed platform types, then start api + frontend.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== GamePrexDef Dev Setup ==="

# ── 1. Start infra (postgres + redis) ────────────────────────────────────────
echo "[1/5] Starting postgres and redis..."
cd "$REPO_ROOT"
docker compose up -d postgres redis
echo "      Waiting for postgres to be healthy..."
until docker compose exec postgres pg_isready -U gameprex -d gameprexdef &>/dev/null; do sleep 1; done
echo "      postgres ready."

# ── 2. Migrate ───────────────────────────────────────────────────────────────
echo "[2/5] Running Alembic migrations..."
cd "$REPO_ROOT/db"
DATABASE_URL="postgresql+asyncpg://gameprex:gameprex_dev@localhost:5432/gameprexdef" \
  alembic upgrade head

# ── 3. Seed platform types ───────────────────────────────────────────────────
echo "[3/5] Seeding platform types..."
cd "$REPO_ROOT/db"
DATABASE_URL="postgresql://gameprex:gameprex_dev@localhost:5432/gameprexdef" \
  python seeds/seed_platforms.py

# ── 4. Install Python deps ───────────────────────────────────────────────────
echo "[4/5] Installing backend Python dependencies..."
cd "$REPO_ROOT/backend"
pip install -e ".[dev]" -q

# ── 5. Install Node deps ─────────────────────────────────────────────────────
echo "[5/5] Installing frontend Node dependencies..."
cd "$REPO_ROOT/frontend"
npm install --silent

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Start the backend:"
echo "  cd backend && DATABASE_URL=postgresql+asyncpg://gameprex:gameprex_dev@localhost:5432/gameprexdef \\"
echo "    REDIS_URL=redis://localhost:6379/0 \\"
echo "    uvicorn api.main:application --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Start the frontend (separate terminal):"
echo "  cd frontend && npm run dev"
echo ""
echo "Login at http://localhost:3000"
echo "  Username: nca"
echo "  Password: gameprex2024"
